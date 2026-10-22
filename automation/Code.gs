/**
 * Northgate Realty enquiry automation (Google Apps Script).
 *
 * Receives the website form (POST), saves a row in a Google Sheet,
 * and emails a notification. Runs in YOUR Google account, so no
 * passwords or keys are stored in the website or this repository.
 *
 * Configure in Project Settings > Script properties:
 *   SHEET_ID     the long ID in your Google Sheet's URL
 *   NOTIFY_EMAIL the address that should receive notifications
 *
 * Status: written but NOT yet deployed or tested. See automation/SETUP.md.
 */

const HEADERS = ["Timestamp", "Submission ID", "Name", "Email", "Phone", "Interest", "Budget", "Contact method", "Message"];
const MAX = { name: 100, email: 150, phone: 25, interest: 80, budget: 40, contact: 10, message: 500 };

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// Stops spreadsheet formulas from running if someone types =, +, - or @ first.
function safe_(value, max) {
  let s = String(value || "").trim().slice(0, max);
  if (/^[=+\-@]/.test(s)) s = "'" + s;
  return s;
}

function doGet() {
  return json_({ ok: true, info: "Northgate Realty enquiry endpoint is running." });
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  let locked = false;
  try {
    const props = PropertiesService.getScriptProperties();
    const sheetId = props.getProperty("SHEET_ID");
    const notify = props.getProperty("NOTIFY_EMAIL");
    if (!sheetId || !notify) return json_({ ok: false, error: "Not configured." });

    const d = JSON.parse((e && e.postData && e.postData.contents) || "{}");

    // Honeypot: real visitors leave this empty. Pretend success to bots.
    if (d.website) return json_({ ok: true });

    const name = safe_(d.name, MAX.name);
    const email = safe_(d.email, MAX.email);
    if (name.length < 2 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) || !d.interest || d.consent !== "on") {
      return json_({ ok: false, error: "Invalid enquiry." });
    }

    // Ignore a repeat of the same submission ID sent within 10 minutes.
    const cache = CacheService.getScriptCache();
    const id = String(d.id || "").slice(0, 60);
    if (id && cache.get("id:" + id)) return json_({ ok: true, duplicate: true });

    lock.waitLock(10000);
    locked = true;

    const sheet = SpreadsheetApp.openById(sheetId).getSheets()[0];
    if (sheet.getLastRow() === 0) sheet.appendRow(HEADERS);
    const row = [
      new Date(), id, name, email,
      safe_(d.phone, MAX.phone), safe_(d.interest, MAX.interest), safe_(d.budget, MAX.budget),
      safe_(d.contact, MAX.contact), safe_(d.message, MAX.message),
    ];
    sheet.appendRow(row);

    MailApp.sendEmail({
      to: notify,
      subject: "New Northgate Realty demo enquiry from " + name,
      body: HEADERS.map((h, i) => h + ": " + row[i]).join("\n"),
    });

    if (id) cache.put("id:" + id, "1", 600);
    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: "Could not save the enquiry." });
  } finally {
    if (locked) lock.releaseLock();
  }
}
