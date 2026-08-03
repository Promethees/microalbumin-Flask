# Easy OKAPI — Privacy Notice (desktop application)

**Controller:** Center for Bioscience and Biotechnology (CBBiotec), University of Science, Vietnam National University Ho Chi Minh City (HCMUS–VNU), 227 Nguyen Van Cu, District 5, Ho Chi Minh City, Vietnam
**Privacy contact:** tqmthong@gmail.com
**Version:** 1.0
**Effective:** 3 August 2026

This notice covers the **desktop** application. The website and hosted web
application are covered by the online policy at
<https://www.easysensorkit.cbbiotec.vn/privacy>, which also applies to the
account you use to obtain a licence.

---

## 1. The short version

Easy OKAPI runs on your machine. Your measurement data stays there. Four things
leave your computer, and three of them only when you choose:

| What | When | Why |
|---|---|---|
| Licence token + hardware fingerprint | Automatic: at activation, at start-up, periodically | Confirm your seat is valid and not revoked |
| Update check + download request | Automatic, and when you accept an update | Confirm your seat, then serve the build |
| Assistant messages | Only when you use the AI assistant | Produce the reply |
| Bug report | Only when you send one, and only what you attach | Diagnose the problem you reported |

We sell nothing, we run no advertising or analytics trackers in the desktop
application, and we do not use your data to train any machine-learning model.

---

## 2. What stays on your machine

- Every CSV, calibration JSON, report, chart and export you create, in the data
  folder you chose at installation.
- The interaction event log under `log/events/<date>/<time>.jsonl` — one file per
  session, recording which actions were taken and when, so a bug can be
  reconstructed. **It is written locally and is never transmitted automatically.**
- Your application settings (`user_settings.json`), including your interface
  language and any AI provider key you configure.
- The activation file (`activation.json`), holding your licence token.
- Serial-port logs from the colorimeter, under `log/`.

None of this is sent to us unless you deliberately send it.

---

## 3. What leaves your machine

### 3.1 Activation and licence checks

At activation, at start-up, and periodically while running, the application sends
our server:

- your **licence token**, and
- the machine's **hardware fingerprint**.

The fingerprint is a SHA-256 digest of a fixed salt combined with a stable
operating-system machine identifier — the Windows `MachineGuid`, the macOS
`IOPlatformUUID`, or the Linux `machine-id`. We receive only the digest. It
identifies a machine to us, but it is not reversible and carries no name, serial
number, MAC address, location, user account or hardware inventory.

We store the fingerprint against your account so that we can enforce a
one-machine seat, record when the machine was last seen, and apply a revocation
or ban if one is issued. Nothing about your files, folders, other software or
network is collected.

### 3.2 Updates

Update checks and downloads send your licence token so we can confirm your seat
before serving a build. Our server records the request in ordinary web logs (IP
address, time, path, status, user agent) for a short rolling window.

### 3.3 The AI assistant

When you use the assistant, your prompt, the recent conversation, and a
structured description of the current screen are sent to a third-party
language-model provider (currently **Groq**) which generates the reply. If you
use our hosted proxy, the request passes through our server; if you configure
your own provider API key, the request goes from your machine directly to that
provider under your own agreement with them, and never reaches us.

Anything you type into the assistant leaves your machine. **Do not paste patient
identifiers, personal data, credentials or confidential third-party information
into it.** We do not use your conversations to train a model.

If you rate an assistant answer, the rating and the exchange it refers to may be
stored so we can find and fix bad answers.

### 3.4 Bug reports

The "Report a Bug" button prepares a zip of the event log files **you** select,
downloads it to your machine, and opens a draft email. You decide whether to
attach the zip and whether to send it. Nothing is transmitted by the application
itself. Before attaching, open the zip and check that it contains nothing you
would not want to share.

### 3.5 Background music

If you use the background-music feature, stream metadata is resolved over the
network. No data about your work, your files or your machine is included.

---

## 4. Legal basis, and how long we keep it

| Data | Basis | Retention |
|---|---|---|
| Licence token, hardware fingerprint, seat records | Performance of our agreement with you; our legitimate interest in protecting the Software from unlicensed use | Until the seat is revoked or your account is deleted |
| Update/licence-check server logs | Legitimate interest in a secure, available service | A short rolling window kept by the hosting platform |
| Assistant messages | Performance of our agreement with you | For the conversation; not retained as a durable transcript, except where you submitted feedback |
| Bug report contents | Your consent, given by sending the email | Until the report is resolved |

---

## 5. Who else sees it

| Provider | Role |
|---|---|
| Heroku (Salesforce) | Hosts the activation, licence and update endpoints, and their database |
| Groq | Runs the language model for the assistant |
| Google (Gmail SMTP) | Delivers account email |

Data is processed on infrastructure operated by providers based in the United
States, so using the licensed features transfers data outside Vietnam. We rely on
those providers' standard contractual clauses and equivalent mechanisms, and we
keep what is transferred to what the feature needs.

Beyond these, we disclose data only where we must: to comply with a law or valid
legal request, to enforce the EULA, or to protect the rights and safety of users
or the public.

---

## 6. Security

- All traffic between the application and our servers is over HTTPS.
- Permanent activation tokens are RS256-signed and verified against a public key
  embedded in the client, so a forged token fails verification offline, without a
  network round trip.
- The activation file is bound to one machine; copying it elsewhere fails.
- Activation and licence-check endpoints are rate-limited.
- Access to production data is limited to the maintainers who need it.

No system is perfectly secure. If you find a vulnerability, please report it to
tqmthong@gmail.com before disclosing it publicly — we will work with you.

---

## 7. Your rights

You may ask us to access, correct, delete, restrict, port or object to the
processing of your personal data, and you may withdraw a consent you gave.

- **Do it yourself.** Uninstall the application to remove it and its local data
  from a machine. Delete your account from the account settings panel on the
  website — that removes your account record, your social sign-in connections and
  every machine seat, and immediately disables the desktop application.
- **Ask us.** Email tqmthong@gmail.com with "Privacy request" in the subject. We
  confirm your identity through the email address on your account and answer
  within 30 days. Requests are free.

If you are unhappy with how we handled a request, tell us first so we can put it
right. You also have the right to complain to your local data protection
authority, and in Vietnam to the competent authority for personal data
protection.

---

## 8. Children

The Software is not directed at children, and we do not knowingly collect
personal data from anyone under 16, or under the minimum age of digital consent
where they live, whichever is higher. Where Easy OKAPI is used in teaching, the
supervising institution is responsible for obtaining any consent its own rules
require.

---

## 9. Changes

We will update this notice when the Software changes. The version number and
effective date above identify the current text, and the current version always
ships with the application and is published at
<https://www.easysensorkit.cbbiotec.vn/privacy>. For a change that materially
affects how we use data you have already given us, we will notify you by email or
in the application at least 14 days before it takes effect, unless a shorter
period is required by law or by a security issue.

---

## 10. Contact

Center for Bioscience and Biotechnology (CBBiotec)
University of Science, Vietnam National University Ho Chi Minh City
227 Nguyen Van Cu, District 5, Ho Chi Minh City, Vietnam

Email: tqmthong@gmail.com
Web: <https://www.easysensorkit.cbbiotec.vn>

See also the End User License Agreement in `legal/EULA.md`.
