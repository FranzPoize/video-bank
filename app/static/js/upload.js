/**
 * upload.js — Async upload with progress popup.
 *
 * Intercepts the upload form, creates an XHR with progress events,
 * and manages a bottom-left popup that persists across page navigations
 * via sessionStorage.
 */
(function () {
  "use strict";

  // Translation helper (falls back to key if translation missing)
  function _(key) {
    return (window.TRANSLATIONS && window.TRANSLATIONS[key]) || key;
  }

  const UPLOAD_FORM_SELECTOR = "#upload-form";
  const POPUP_ID = "upload-popup";
  const STORAGE_KEY = "upload-active";

  // ── Popup helpers ──────────────────────────────────────────────

  /** Return the popup element, creating it if missing (defensive). */
  function getPopup() {
    let popup = document.getElementById(POPUP_ID);
    if (!popup) {
      popup = document.createElement("div");
      popup.id = POPUP_ID;
      popup.style.cssText =
        "position:fixed;bottom:1rem;left:1rem;z-index:9999;" +
        "background:#1a1a2e;color:#fff;padding:0.75rem 1rem;" +
        "border-radius:8px;min-width:280px;box-shadow:0 4px 12px rgba(0,0,0,0.3);" +
        "font-size:0.9rem;display:none;";
      document.body.appendChild(popup);
    }
    return popup;
  }

  function showPopup() {
    getPopup().style.display = "block";
  }

  function hidePopup() {
    getPopup().style.display = "none";
  }

  function setPopupContent(html) {
    getPopup().innerHTML = html;
  }

  // ── Progress bar HTML ──────────────────────────────────────────

  function progressBarHTML(pct) {
    const clamped = Math.min(100, Math.max(0, pct));
    return (
      '<div style="margin-top:6px;height:6px;background:#333;border-radius:3px;overflow:hidden;">' +
      '<div style="height:100%;width:' +
      clamped +
      '%;background:#4361ee;border-radius:3px;transition:width 0.2s;"></div>' +
      "</div>"
    );
  }

  // ── sessionStorage helpers ─────────────────────────────────────

  function saveState(filename, status) {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ filename: filename, status: status })
      );
    } catch (_) {
      // sessionStorage full — upload still works, just no persistence
    }
  }

  function clearState() {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch (_) {
      // ignore
    }
  }

  function restoreState() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const state = JSON.parse(raw);
      if (state && state.filename) {
        showPopup();
        setPopupContent(
          '<div style="display:flex;align-items:center;gap:0.5rem;">' +
            '<span style="flex:1;">' +
            escapeHtml(state.filename) +
            "</span>" +
            '<span style="color:#888;font-size:0.8rem;">' +
            (state.status === "completed"
              ? "&#10003; " + _("upload.completed")
              : state.status === "failed"
                ? "&#10007; " + _("upload.failed")
                : "&#8987; " + _("upload.resumed")) +
            "</span></div>" +
            (state.status === "uploading"
              ? progressBarHTML(0)
              : state.status === "failed"
                ? '<button onclick="location.reload()" style="margin-top:6px;padding:2px 8px;font-size:0.8rem;background:#e63946;color:#fff;border:none;border-radius:4px;cursor:pointer;">' + _("btn.retry") + '</button>'
                : "")
        );
      }
    } catch (_) {
      // ignore malformed state
    }
  }

  // ── Escaping ───────────────────────────────────────────────────

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // ── Main upload handler ────────────────────────────────────────

  function handleUpload(event) {
    const form = event.target;
    const formData = new FormData(form);
    const filename =
      formData.get("file") && formData.get("file").name
        ? formData.get("file").name
        : _("upload.untitled");

    event.preventDefault();

    const xhr = new XMLHttpRequest();
    const popup = getPopup();

    // ── Progress ──
    xhr.upload.addEventListener("progress", function (e) {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        showPopup();
        setPopupContent(
          '<div style="display:flex;align-items:center;gap:0.5rem;">' +
            '<span style="flex:1;">' +
            escapeHtml(filename) +
            "</span>" +
            '<span style="color:#888;font-size:0.8rem;">' +
            pct +
            "%</span></div>" +
            progressBarHTML(pct)
        );
        saveState(filename, "uploading");
      }
    });

    // ── Load / complete ──
    xhr.addEventListener("load", function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        // Success
        setPopupContent(
          '<div style="display:flex;align-items:center;gap:0.5rem;">' +
            '<span style="color:#2d6a4f;">&#10003;</span>' +
            '<span style="flex:1;">' +
            escapeHtml(filename) +
            "</span>" +
            '<span style="color:#2d6a4f;font-size:0.8rem;">' + _("upload.completed") + '</span></div>'
        );
        saveState(filename, "completed");

        // Redirect to home after brief delay
        setTimeout(function () {
          clearState();
          window.location.href = "/";
        }, 1500);
      } else {
        // Server error
        setPopupContent(
          '<div style="display:flex;align-items:center;gap:0.5rem;">' +
            '<span style="color:#e63946;">&#10007;</span>' +
            '<span style="flex:1;">' +
            escapeHtml(filename) +
            "</span>" +
            '<span style="color:#e63946;font-size:0.8rem;">' + _("upload.failed") + '</span></div>' +
            '<button onclick="location.reload()" style="margin-top:6px;padding:2px 8px;font-size:0.8rem;background:#e63946;color:#fff;border:none;border-radius:4px;cursor:pointer;">' + _("btn.retry") + '</button>'
        );
        saveState(filename, "failed");
      }
    });

    // ── Error / network failure ──
    xhr.addEventListener("error", function () {
      setPopupContent(
        '<div style="display:flex;align-items:center;gap:0.5rem;">' +
          '<span style="color:#e63946;">&#10007;</span>' +
          '<span style="flex:1;">' +
          escapeHtml(filename) +
          "</span>" +
          '<span style="color:#e63946;font-size:0.8rem;">' + _("upload.network_error") + '</span></div>' +
          '<button onclick="location.reload()" style="margin-top:6px;padding:2px 8px;font-size:0.8rem;background:#e63946;color:#fff;border:none;border-radius:4px;cursor:pointer;">' + _("btn.retry") + '</button>'
      );
      saveState(filename, "failed");
    });

    // ── Send ──
    xhr.open("POST", form.action);
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    xhr.send(formData);
  }

  // ── Init ───────────────────────────────────────────────────────

  function init() {
    // Restore any in-flight upload popup
    restoreState();

    // Hook into the upload form
    const form = document.querySelector(UPLOAD_FORM_SELECTOR);
    if (form) {
      form.addEventListener("submit", handleUpload);
    }
  }

  // Wait for DOM to be ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
