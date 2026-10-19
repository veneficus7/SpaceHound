/* Talks to the Python backend: pywebview's js_api in the desktop app,
   or the token-protected HTTP bridge in --browser mode. */

const API = (() => {
  const token = new URLSearchParams(location.search).get("token");
  let mode = null;

  const ready = new Promise((resolve) => {
    if (token) { mode = "http"; resolve(mode); return; }
    const done = () => { mode = "webview"; resolve(mode); };
    if (window.pywebview && window.pywebview.api && window.pywebview.api.app_info) done();
    else {
      window.addEventListener("pywebviewready", done, { once: true });
      // belt and braces: some WebView2 builds fire the event before our listener exists
      const poll = setInterval(() => {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.app_info) { clearInterval(poll); done(); }
      }, 100);
    }
  });

  async function call(name, ...args) {
    await ready;
    if (mode === "webview") {
      const fn = window.pywebview.api[name];
      if (!fn) throw new Error(`Unknown API method: ${name}`);
      return fn(...args);
    }
    const res = await fetch(`/api/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-SpaceHound-Token": token },
      body: JSON.stringify({ args }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Request failed");
    return data.result;
  }

  // Proxy so callers can write API.children(id) instead of API.call("children", id)
  return new Proxy({ call, ready }, {
    get(target, prop) {
      if (prop in target) return target[prop];
      return (...args) => call(prop, ...args);
    },
  });
})();

/* Poll a background job until it finishes. onProgress(status) is called on every tick. */
async function waitJob(jobId, onProgress, interval = 220) {
  for (;;) {
    const st = await API.job(jobId);
    if (!st) throw new Error("Job vanished");
    if (onProgress) onProgress(st);
    if (st.state === "done") return st.result;
    if (st.state === "error") throw new Error(st.error || "Job failed");
    if (st.state === "cancelled") { const e = new Error("Cancelled"); e.cancelled = true; throw e; }
    await U.sleep(interval);
  }
}
