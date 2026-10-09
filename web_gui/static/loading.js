// Shared by index.html and map.html: a spinner centered on the page, shown while any fetch()
// is in flight. Wraps window.fetch once, so every request on the page is
// covered without each call site opting in -- load this before app.js/map.js.
// Shown only after SHOW_DELAY_MS, so fast requests don't make it flicker.
(function () {
    const SHOW_DELAY_MS = 250;
    // Created here rather than in each page's HTML. A full-page overlay, so
    // the page can't be clicked until pending requests finish.
    const indicator = document.createElement("div");
    indicator.id = "loading-indicator";
    indicator.className = "d-none";
    indicator.setAttribute("role", "status");
    indicator.innerHTML = '<div class="spinner-border text-secondary"><span class="visually-hidden">Loading</span></div>';
    document.body.appendChild(indicator);
    let pending = 0;
    let showTimer = null;

    function update() {
        if (pending > 0 && showTimer === null && indicator.classList.contains("d-none")) {
            showTimer = setTimeout(() => {
                showTimer = null;
                if (pending > 0) {
                    indicator.classList.remove("d-none");
                    document.body.classList.add("page-loading");
                }
            }, SHOW_DELAY_MS);
        } else if (pending === 0) {
            clearTimeout(showTimer);
            showTimer = null;
            indicator.classList.add("d-none");
            document.body.classList.remove("page-loading");
        }
    }

    const originalFetch = window.fetch.bind(window);
    window.fetch = function (...args) {
        pending += 1;
        update();
        // Counted until the response *body* has arrived, not just its
        // headers -- callers almost always read it (r.json()), and a big
        // response can take a while after the headers.
        const done = () => {
            pending -= 1;
            update();
        };
        return originalFetch(...args).then(
            (response) => {
                response.clone().arrayBuffer().then(done, done);
                return response;
            },
            (error) => {
                done();
                throw error;
            }
        );
    };
})();
