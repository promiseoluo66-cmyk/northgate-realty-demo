// Northgate Realty - demo site script (plain JavaScript, no libraries).

// To connect real enquiries, paste your Google Apps Script Web App URL here.
// It looks like https://script.google.com/macros/s/XXXX/exec
// This URL is public by design. Never put passwords or private keys in this file.
// While empty, the form runs in demo mode and sends nothing.
const ENDPOINT = "";

const $ = (s, r = document) => r.querySelector(s);
$("#year").textContent = new Date().getFullYear();

// Mobile menu
const menuBtn = $("#menuBtn");
const nav = $("#nav");
function setMenu(open) {
  nav.classList.toggle("open", open);
  menuBtn.setAttribute("aria-expanded", String(open));
}
menuBtn.addEventListener("click", () => setMenu(!nav.classList.contains("open")));
nav.addEventListener("click", (e) => { if (e.target.closest("a")) setMenu(false); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && nav.classList.contains("open")) { setMenu(false); menuBtn.focus(); }
});
window.matchMedia("(min-width: 960px)").addEventListener("change", (m) => { if (m.matches) setMenu(false); });

// Form
const form = $("#enquiryForm");
const status = $("#status");
const submitBtn = $("#submitBtn");
const message = $("#message");
const count = $("#count");
let submitting = false;
let submissionId = null;

message.addEventListener("input", () => { count.textContent = message.value.length + " / 500"; });

document.querySelectorAll("[data-interest]").forEach((a) => {
  a.addEventListener("click", () => { $("#interest").value = a.dataset.interest; });
});

const rules = {
  name: (v) => (v.trim().length >= 2 ? "" : "Enter your full name."),
  email: (v) => (/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()) ? "" : "Enter a valid email address, like name@example.com."),
  phone: (v) => (!v.trim() || /^[+\d][\d\s().-]{6,19}$/.test(v.trim()) ? "" : "Use only digits, spaces, + or - in the phone number, or leave it blank."),
  interest: (v) => (v ? "" : "Choose what you are interested in."),
  message: (v) => (v.length <= 500 ? "" : "Keep your message to 500 characters or fewer."),
  consent: (v, el) => (el.checked ? "" : "Tick the box so we know we may reply to you."),
};

function check(field) {
  const el = form.elements[field];
  const msg = rules[field](el.value, el);
  $("#e-" + field).textContent = msg;
  if (msg) el.setAttribute("aria-invalid", "true"); else el.removeAttribute("aria-invalid");
  return !msg;
}

Object.keys(rules).forEach((f) => {
  const el = form.elements[f];
  const recheck = () => { if (el.getAttribute("aria-invalid")) check(f); };
  el.addEventListener("input", recheck);
  el.addEventListener("change", recheck);
  if (el.tagName !== "SELECT" && el.type !== "checkbox") el.addEventListener("blur", () => { if (el.value) check(f); });
});

function show(text, bad) {
  status.textContent = text;
  status.classList.toggle("bad", !!bad);
  status.focus();
}

function newId() {
  return (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (submitting) return;
  status.textContent = "";
  const results = Object.keys(rules).map((f) => [f, check(f)]);
  const firstBad = results.find(([, ok]) => !ok);
  if (firstBad) {
    form.elements[firstBad[0]].focus();
    show("Please fix the highlighted fields and try again.", true);
    return;
  }
  if (!ENDPOINT) {
    show("This portfolio demo form has been validated, but no enquiry was sent. Connect the automation endpoint to receive real submissions.");
    return;
  }
  submitting = true;
  submitBtn.disabled = true;
  submitBtn.textContent = "Sending...";
  submissionId = submissionId || newId();
  const data = Object.fromEntries(new FormData(form).entries());
  data.id = submissionId;
  try {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "text/plain;charset=utf-8" },
      body: JSON.stringify(data),
    });
    const out = await res.json();
    if (out && out.ok) {
      show("Thank you. Your enquiry was received.");
      form.reset();
      count.textContent = "0 / 500";
      submissionId = null;
    } else {
      show("The enquiry could not be saved. Please try again later.", true);
    }
  } catch (err) {
    show("We could not confirm that your enquiry was received. Please check your connection and try again.", true);
  } finally {
    submitting = false;
    submitBtn.disabled = false;
    submitBtn.textContent = "Send enquiry";
  }
});
