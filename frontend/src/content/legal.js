/* Copyright 2017-present, The Visdom Authors */

export const CONTROLLER = {
  name: 'FOSSASIA PTE. LTD.',
  address: '12 Eu Tong Sen Street #08-169, Singapore 059819',
  email: 'office@fossasia.org',
};

export const UPDATED = '23 October 2026';

export const PRIVACY = [
  {
    heading: 'Who runs this service',
    body: [
      `visdom.dev is run by ${CONTROLLER.name}, ${CONTROLLER.address}. It decides what is collected here and why, and it is who to contact about any of it, at ${CONTROLLER.email}.`,
      'visdom.dev is a hosted version of visdom, an open source tool for watching machine learning experiments as they run.',
    ],
  },
  {
    heading: 'What we hold about you',
    body: [
      'Your account: the email address you signed up with, the username shown to people you share a workspace with, and your password. Your password is stored as a hash, which means we cannot read it and cannot tell you what it is.',
      'What you send: the plots, values and text your code writes into your workspaces. We treat this as yours. Nobody outside your workspace sees it, and we do not look through it except when you ask for help with a specific problem.',
      'How much you use: how many minutes a workspace was written to, how many writes it took, and how much disk it holds. We need these to apply the limits of your plan.',
      'If you buy a paid plan: your payment details, whether a card, a bank account or another method Stripe offers, go straight to Stripe and never reach us. We keep a reference to your Stripe customer and subscription, which plan it is for, whether it is paid up, and when it renews.',
      'Technical records: the address your requests come from, the browser you used, and the time, kept in server logs. Actions taken by our staff in the admin console are recorded with the staff account that took them.',
    ],
  },
  {
    heading: 'Why we hold it',
    body: [
      'To run the service: sign you in, keep your workspaces separate, and show you your plots.',
      'To keep it working and secure: find faults, investigate abuse, and stop one account from taking the service down for everyone.',
      'To apply your plan: counting usage is how limits work, and a paid plan is charged through Stripe.',
      'We do not sell any of it, we do not use it for advertising, and we do not run analytics or tracking scripts on this site.',
    ],
  },
  {
    heading: 'Where it is kept',
    body: [
      'The service runs on Oracle Cloud Infrastructure in Mumbai, India. Backups are copied to Amazon Web Services, also in Mumbai, India.',
      'So although the organisation is registered in Singapore, your data is stored in India. If you are in the EU or UK, this means your data is transferred outside those regions.',
    ],
  },
  {
    heading: 'How long we keep it',
    body: [
      'Your account details are kept while the account exists.',
      'Plot data is kept for at least as long as your plan says, counted from when an environment was last written to. The free plan keeps 7 days and the pro plan keeps 90. After that, older environments may be removed automatically.',
      'Backups are kept for 90 days and then deleted, so data can remain in a backup for up to 90 days after you remove it from the service.',
      'Usage records are kept while the workspace they describe exists, and are deleted with it. Deleting your account deletes your workspaces, so their usage records go too.',
      'Billing records are kept while the account exists and deleted with it. Stripe keeps its own record of payments, as the law requires of a payment provider.',
      'Server logs are kept in files of a fixed size. The oldest entries are overwritten as new ones arrive, so logs are not kept indefinitely and are not kept per account.',
    ],
  },
  {
    heading: 'Who else is involved',
    body: [
      'Oracle Cloud Infrastructure hosts the service. Amazon Web Services stores the backups. Cloudflare answers DNS for the visdom.dev name.',
      'When email is switched on, an email provider will deliver messages such as password resets and invitations. This page will name it before that happens.',
      'Stripe takes payment for paid plans. It receives your email address and the payment details you enter in its payment form.',
      'None of them are given your data for their own purposes, except that Stripe keeps payment records and checks payments for fraud, as a payment provider must.',
    ],
  },
  {
    heading: 'What you can ask for',
    body: [
      'A copy of what we hold about you, a correction, or deletion of your account and its contents.',
      'You can delete workspaces yourself from the console at any time. You can also delete your whole account from your profile. It stops working straight away and is removed for good 30 days later, along with any workspace nobody else uses. Signing in during those 30 days cancels it.',
      'If you think we are handling your data wrongly, tell us first, and you also have the right to complain to a data protection authority.',
    ],
  },
  {
    heading: 'Keeping it safe',
    body: [
      'Traffic to the site is encrypted. Passwords and API keys are stored as hashes rather than as themselves, so a copy of the database does not hand anyone your password or a working key.',
      'This is a small service run by a small team, and it is being tested in the open. Treat it accordingly: do not put anything confidential in it.',
    ],
  },
  {
    heading: 'Changes to this page',
    body: [
      'If this changes in a way that matters, the date at the top changes with it, and anyone signed in will be told.',
    ],
  },
];

export const COOKIES = [
  {
    heading: 'What we set',
    body: [
      'Two cookies for everyone who uses the site, both needed to keep you signed in, and nothing else.',
      'session_token, which proves who you are on each request. It lasts 15 minutes and is renewed while you are using the site.',
      'refresh_token, which is what gets you a new session_token without typing your password again. It lasts 7 days.',
      'Both are set so that scripts on the page cannot read them. visdom.dev only works over an encrypted connection: a request made without one is sent on to the encrypted address, and browsers are told to use only that address from then on.',
      'Our staff get one more cookie, session, when they sign in to the admin console. It keeps them signed in there and is not set for anyone else.',
    ],
  },
  {
    heading: 'What we do not set',
    body: [
      'No analytics, no advertising and no tracking. Nothing here follows you to other sites.',
      'The one exception is paying for a plan. When you open the payment form, Stripe loads it and sets its own cookies, which it uses to stop fraud. They are not set anywhere else on this site.',
      'That is why this site does not ask you to accept cookies: the two it sets are needed to sign in, and Stripe\'s are needed to pay.',
    ],
  },
  {
    heading: 'Removing them',
    body: [
      'Signing out clears both. You can also clear them in your browser settings, which signs you out.',
      'If you block them, the site will not be able to keep you signed in.',
    ],
  },
];
