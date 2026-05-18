/**
 * upload.js — Async upload with Franken UI notifications.
 *
 * Intercepts the upload form, creates an XHR with progress events,
 * and uses UIkit.notification() for user feedback while maintaining
 * a hidden state div for sessionStorage persistence across HTMX navigations.
 */
(function () {
  "use strict";

  function _(key) {
    return (window.TRANSLATIONS && window.TRANSLATIONS[key]) || key;
  }

  var UPLOAD_FORM_SELECTOR = "#upload-form";
  var STATE_DIV_ID = "upload-popup";
  var STORAGE_KEY = "upload-active";
  var activeNotification = null;

  // ── State persistence (hidden div + sessionStorage) ──

  function getStateDiv() {
    var el = document.getElementById(STATE_DIV_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = STATE_DIV_ID;
      el.hidden = true;
      document.body.appendChild(el);
    }
    return el;
  }

  function saveState(filename, status) {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ filename: filename, status: status })
      );
    } catch (_) {}
  }

  function clearState() {
    try { sessionStorage.removeItem(STORAGE_KEY); } catch (_) {}
  }

  function restoreState() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      var state = JSON.parse(raw);
      if (state && state.filename) {
        var msg = state.filename + " — " +
          (state.status === "completed"
            ? _("upload.completed")
            : state.status === "failed"
              ? _("upload.failed")
              : _("upload.resumed"));
        UIkit.notification({
          message: msg,
          status: state.status === "completed" ? "primary" : "destructive",
          pos: "bottom-left",
          timeout: state.status === "completed" ? 5000 : 0
        });
      }
    } catch (_) {}
  }

  // ── Progress notification ──

  function showNotification(message, status, timeout) {
    if (activeNotification) {
      activeNotification.close();
    }
    activeNotification = UIkit.notification({
      message: message,
      status: status || "primary",
      pos: "bottom-left",
      timeout: timeout || 5000
    });
  }

  // ── Escaping ──

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // ── Main upload handler ──

  function handleUpload(event) {
    var form = event.target;
    var formData = new FormData(form);
    var filename =
      formData.get("file") && formData.get("file").name
        ? formData.get("file").name
        : _("upload.untitled");

    event.preventDefault();

    var xhr = new XMLHttpRequest();

    // ── Progress ──
    xhr.upload.addEventListener("progress", function (e) {
      if (e.lengthComputable) {
        var pct = Math.round((e.loaded / e.total) * 100);
        showNotification(
          escapeHtml(filename) + " " + pct + "%",
          "primary",
          0
        );
        saveState(filename, "uploading");
      }
    });

    // ── Load / complete ──
    xhr.addEventListener("load", function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        showNotification(
          "✓ " + escapeHtml(filename) + " — " + _("upload.completed"),
          "primary",
          5000
        );
        saveState(filename, "completed");
        activeNotification = null;

        setTimeout(function () {
          clearState();
          window.location.href = "/";
        }, 1500);
      } else {
        showNotification(
          "✗ " + escapeHtml(filename) + " — " + _("upload.failed"),
          "destructive",
          0
        );
        saveState(filename, "failed");
      }
    });

    // ── Error / network failure ──
    xhr.addEventListener("error", function () {
      showNotification(
        "✗ " + escapeHtml(filename) + " — " + _("upload.network_error"),
        "destructive",
        0
      );
      saveState(filename, "failed");
    });

    // ── Send ──
    xhr.open("POST", form.action);
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    xhr.send(formData);
  }

  // ── Init ──

  function init() {
    restoreState();

    var form = document.querySelector(UPLOAD_FORM_SELECTOR);
    if (form) {
      form.addEventListener("submit", handleUpload);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
