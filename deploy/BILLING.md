# Taking payment for plans

Paid plans are sold through Stripe. The payment form is Stripe's own, shown
inside the Billing tab, so payment details never reach this server. What the server keeps
is the Stripe customer and subscription ids, the plan, its status and its
renewal date.

Until the two Stripe keys and the webhook secret are all set, nothing can be
bought: paid plans show "Not available yet" and only free plans can be picked.
Without the webhook secret, changes made in Stripe's customer portal could not
reach the gateway, so payments stay off and the gateway says so when it starts.

## How it behaves

- **Buying.** A user on a free plan clicks Upgrade, pays in the form, and is
  moved onto the plan as soon as Stripe confirms the payment.
- **Changing or cancelling.** A paying user clicks Manage billing, which opens
  Stripe's customer portal. Every change made there reaches the gateway through
  the webhook.
- **The plan follows the subscription.** It stays while the subscription is
  `active`, `trialing` or `past_due` (Stripe is still retrying a failed card).
  When the subscription ends, the account goes back to the free plan.
- **Staff assignments stay.** A plan given from the admin console is left alone
  when an old subscription ends.
- **Deleting an account.** Asking to delete it stops the renewal, and the
  delete form says so. Signing in before the deadline asks whether to turn the
  renewal back on. Removing it for good cancels the subscription first. If
  Stripe cannot be reached, neither step goes ahead.
- **Manage billing** shows once the account has bought a plan, even one that
  has since ended, so past invoices stay reachable.

The webhook never trusts the event it is sent: it reads the subscription back
from Stripe before changing anything.

## Setting it up

Do this in test mode first. Test mode and live mode have separate keys, prices
and webhooks.

1. **A price for each paid plan.** In Stripe, go to Product catalog and add a
   product, for example "Visdom Pro", with a recurring monthly price matching
   the plan. Copy the price id, which starts with `price_`.
2. **Link the plan to the price.** Store the id on the plan. A plan without
   one cannot be bought.
   ```
   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
   UPDATE plans SET stripe_price_id = 'price_...' WHERE id = 'pro';
   SQL
   ```
3. **Keys.** In Developers, then API keys, copy the publishable key (`pk_test_`)
   and the secret key (`sk_test_`) into `.env`:
   ```
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_SECRET_KEY=sk_test_...
   ```
4. **Webhook.** In Developers, then Webhooks, add an endpoint at
   `https://visdom.dev/api/v1/billing/webhook` with these events:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `customer.subscription.paused`
   - `customer.subscription.resumed`

   Copy its signing secret (`whsec_`) into `.env` as `STRIPE_WEBHOOK_SECRET`.
5. **Customer portal.** In Settings, then Billing, then Customer portal, turn on
   cancelling (at the end of the period), updating the payment method and
   invoice history. To let people move between paid plans there, add those
   products under Subscriptions.
6. **Restart the gateway** so it reads the new settings:
   ```
   docker compose up -d gateway
   ```

## Trying it locally

Install the Stripe CLI, sign in with `stripe login`, then forward events to the
local gateway:

```
stripe listen --forward-to localhost:8085/api/v1/billing/webhook \
  --events checkout.session.completed,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,customer.subscription.paused,customer.subscription.resumed
```

It prints a `whsec_` secret for this session. Put it in `STRIPE_WEBHOOK_SECRET`
in `gateway/.env` when the gateway runs with uvicorn, which is what listens on
port 8085, or in the root `.env` when it runs under docker compose.

Test cards, with any future expiry date and any CVC:

| Card | What happens |
|---|---|
| `4242 4242 4242 4242` | Pays |
| `4000 0025 0000 3155` | Asks for 3D Secure, then pays |
| `4000 0000 0000 0341` | Accepted as the new card in Manage billing, but the next renewal is declined, so the plan goes `past_due`. A Stripe test clock moves time on to that renewal. |
| `4000 0000 0000 9995` | Declined |

## Going live

Repeat steps 1 to 5 in live mode. The live price ids are different from the
test ones, so update each plan's Stripe price at the same time as the keys
change.
