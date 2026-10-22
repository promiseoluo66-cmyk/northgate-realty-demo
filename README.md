# Northgate Realty - Enquiry Automation Demo

A concept website for a **fictional** real-estate agency, built by RapidPixel as portfolio project 2. All listings, prices and places are made up. It is **not** a real agency and has no real addresses, reviews, sales or credentials.

| | |
|---|---|
| **Repository** | https://github.com/promiseoluo66-cmyk/northgate-realty-demo |
| **Live demo** | Not published or verified yet (see "Publish") |
| **First project** | https://github.com/promiseoluo66-cmyk/sparkle-clean-co |
| **Built with** | HTML, CSS, JavaScript, Google Apps Script (planned), GitHub Pages |
| **Cost** | Free. No paid tools or services. |

## What this demo shows

- A mobile-first real-estate landing page with demo listings
- A property enquiry form with client-side validation, a character limit, a consent box, a hidden spam trap, and protection against double submission
- A planned workflow: form -> Google Apps Script -> Google Sheet -> email notification

## What is done and what is not

| Feature | Status |
|---|---|
| Website, menu, listings, process, footer | Built (not yet tested in a browser) |
| Form validation and demo-mode message | Built (not yet tested in a browser) |
| Duplicate-submission handling (button lock and submission ID) | Built (not yet tested) |
| Google Apps Script (`automation/Code.gs`) | Written, **not deployed, not tested** |
| Google Sheets saving | **Not connected. Not working yet.** |
| Email notification | **Not connected. Not working yet.** |
| GitHub Pages | **Not enabled yet** |

**The form does not send real enquiries yet.** In demo mode it says so after a valid submission. It never claims delivery unless the script replies that it saved the enquiry.

## Files

| File | Purpose |
|---|---|
| `index.html` | Page content and the form |
| `style.css` | Styling (colours are variables at the top) |
| `script.js` | Menu, validation, and the `ENDPOINT` setting |
| `automation/Code.gs` | The Google Apps Script that saves and emails enquiries |
| `automation/SETUP.md` | Step-by-step setup, test plan, limits |
| `.gitignore` | Keeps private files like `.env` out of the repo |

No `.env.example` is needed. The only settings are two Script properties inside Google (`SHEET_ID` and `NOTIFY_EMAIL`), documented in `automation/SETUP.md`.

## Preview

Download the files into one folder and open `index.html` in a browser.

## Publish free from your phone

1. Open the repository on GitHub and tap **Settings**.
2. Tap **Pages**.
3. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
4. Choose branch **main** and folder **/ (root)**, then **Save**.
5. Wait a few minutes. The address appears at the top of the Pages screen, expected to be https://promiseoluo66-cmyk.github.io/northgate-realty-demo/

## How the workflow is meant to work

1. A visitor completes the form and the page checks the answers.
2. The page sends the enquiry to your Google Apps Script web app.
3. The script checks it again, saves a row in your Google Sheet, and emails you.
4. The script replies, and the page shows success only if the reply says it was saved.

Full steps and the test plan are in `automation/SETUP.md`.

## Accounts, secrets and limits

- **Needs:** a free Google account. Nothing else.
- **Secrets:** none go in this repo. The sheet ID and your email live in Script properties inside Google. The web app URL in `script.js` is public by design.
- **Limit checked:** Google's quota page lists 100 email recipients per day for consumer accounts. It says limits can change without notice.
- **Risk:** the web app URL is public, so spam is possible. Basic checks are included but are not a full defence.
- **Alternatives:** other free form services exist. Their free-plan limits were not verified here.

## Safe way to test a real enquiry

Use a made-up name and an email you control. Do not enter real personal data, because this concept site has no privacy policy. Follow the test plan in `automation/SETUP.md`.

## Checks still to do

- Open the page on a phone (about 320-390px wide) and on desktop.
- Open and close the menu and tap every link and button.
- Submit the form empty, with a bad email, without a property interest, without consent, and with a valid entry.
- Deploy the script and run the full test plan before saying the automation works.
