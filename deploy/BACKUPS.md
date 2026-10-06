# Nightly backups

One archive a night, holding everything needed to rebuild the deployment from
nothing, uploaded to S3 and kept for a week on the box as well.

| In the archive | Where it comes from | Why |
|---|---|---|
| `db.dump` | `pg_dump -Fc` of the Postgres container | accounts, workspaces, keys, memberships, usage |
| `envs.tar` | the `visdom_data` volume, mounted at `/data/envs` | every environment's plots, one JSON per env |
| `env` | `.env` beside `docker-compose.yml` | database password, JWT secret, admin secret, SMTP settings |

The third one is why the bucket must stay private. Without it a rebuilt box
cannot read its own database.

## One time, in the AWS console

1. **Pick a region** (top right) and keep it. `ap-south-1` (Mumbai) is the
   closest to home. Every step below happens inside that region.
2. **S3 → Create bucket.** Name it something unique, for example
   `visdom-dev-backups-<something>`. Leave **Block all public access** on.
   Turn **Bucket Versioning** on, so a bad night cannot overwrite a good one.
   Default encryption is already on.
3. **The bucket → Management → Create lifecycle rule**, applied to the whole
   bucket: expire current versions after 90 days, permanently delete
   non-current versions after 30. Without this the bucket grows forever.
4. **IAM → Users → Create user**, name `visdom-dev-backup`, no console access.
   On the permissions step choose **Attach policies directly → Create inline
   policy → JSON** and paste this, with your bucket name in it:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "UploadBackupsOnly",
         "Effect": "Allow",
         "Action": ["s3:PutObject", "s3:AbortMultipartUpload"],
         "Resource": "arn:aws:s3:::BUCKET-NAME/*"
       }
     ]
   }
   ```

   Upload and nothing else. No read, no delete, no listing. If the key is ever
   taken off the box, whoever has it still cannot read a single backup, and
   cannot destroy the ones already there.
5. **That user → Security credentials → Create access key → Application
   running outside AWS.** Copy the access key id and the secret. The secret is
   shown once.
6. **Billing → Budgets → Create budget → Zero spend budget**, with your email.
   The nightly archive is well under a megabyte, so this should never fire.
   Set it anyway; it is the cheapest habit in AWS.

## One time, on the box

Install the AWS CLI:

```bash
sudo apt-get update && sudo apt-get install -y unzip
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install && aws --version
```

Write the settings, including the two keys. This file is root-only and is
deliberately **not** the stack's `.env`, so the archive never carries the
credentials used to upload it:

```bash
sudo install -m 600 /dev/null /etc/visdom-backup.env
sudo tee /etc/visdom-backup.env >/dev/null <<'SETTINGS'
BACKUP_BUCKET=visdom-dev-backups-<something>
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=<access key id>
AWS_SECRET_ACCESS_KEY=<secret access key>
PING_URL=
SETTINGS
```

Install the script and the timer:

```bash
cd ~/app/visdom-dev && git pull
sudo install -m 755 deploy/backup.sh /usr/local/bin/visdom-backup
sudo install -m 644 deploy/visdom-backup.service deploy/visdom-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now visdom-backup.timer
```

Run one now and watch it:

```bash
sudo systemctl start visdom-backup.service
journalctl -u visdom-backup -n 20 --no-pager
systemctl list-timers visdom-backup --no-pager
```

The last line of a good run names the size and the S3 key it wrote.

## Knowing it ran

`PING_URL` is optional and worth setting. Make a check at healthchecks.io with
a period of one day and a grace of six hours, put its ping URL in
`/etc/visdom-backup.env`, and you get an email when a run fails **and** when a
run never happens at all, which is the case a box that is simply dead will
never tell you about itself.

## Restoring

Fetch an archive from the console or from a laptop that has your own AWS
credentials. The backup user cannot read or list; that is on purpose.

```bash
aws s3 ls s3://<bucket>/visdom-dev/ --recursive | tail
aws s3 cp s3://<bucket>/visdom-dev/2026/09/visdom-dev-<stamp>.tar.gz .
sha256sum visdom-dev-<stamp>.tar.gz     # compare with the .sha256 object
tar -xzf visdom-dev-<stamp>.tar.gz      # gives db.dump, envs.tar, env
```

Database, into the running stack:

```bash
cd ~/app/visdom-dev
docker compose cp db.dump db:/tmp/db.dump
docker compose exec -T db pg_restore -U visdom -d visdom_dev --clean --if-exists /tmp/db.dump
docker compose restart gateway
```

Plot data, onto the volume the three visdom containers share:

```bash
docker run --rm -i -v visdom-dev_visdom_data:/envs busybox tar -xf - -C /envs < envs.tar
docker compose restart visdom-1 visdom-2 visdom-3
```

On a fresh box, put `env` back as `.env` first, then `docker compose up -d`,
then restore as above.

## Drill it

A backup nobody has restored is a guess. Once a month, restore the newest
archive into a scratch database on the box and count what came back:

```bash
docker compose exec -T db psql -U visdom -d visdom_dev -c 'create database restore_drill'
docker compose cp db.dump db:/tmp/db.dump
docker compose exec -T db pg_restore -U visdom -d restore_drill /tmp/db.dump
docker compose exec -T db psql -U visdom -d restore_drill -c 'select count(*) from users'
docker compose exec -T db psql -U visdom -d visdom_dev -c 'drop database restore_drill'
```

If that count matches the live one, the archive is real.
