// Shared by index.html and map.html: renders a task/pipeline description
// collapsed to 2 lines with a "Show more/less" toggle, but only when the text
// actually overflows 2 lines -- short descriptions get no toggle at all.
function renderDescription(textEl, toggleEl, text) {
    textEl.textContent = text || "";
    textEl.classList.remove("collapsible", "collapsed");
    textEl.onclick = null;
    toggleEl.classList.add("d-none");
    toggleEl.textContent = "";
    toggleEl.onclick = null;

    if (!text) return;

    textEl.classList.add("collapsed");

    const toggle = (e) => {
        e.preventDefault();
        const collapsed = textEl.classList.toggle("collapsed");
        toggleEl.textContent = collapsed ? "Show more ▾" : "Show less ▴";
    };

    // Collapsing changes scrollHeight vs clientHeight only after layout, so
    // defer the overflow check a frame rather than measuring synchronously.
    requestAnimationFrame(() => {
        if (textEl.scrollHeight > textEl.clientHeight + 1) {
            textEl.classList.add("collapsible");
            toggleEl.classList.remove("d-none");
            toggleEl.textContent = "Show more ▾";
            textEl.onclick = toggle;
            toggleEl.onclick = toggle;
        }
    });
}
