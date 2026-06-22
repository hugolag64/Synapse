/* ══════════════════════════════════════════════
   Synapse — scripts globaux v2
   ══════════════════════════════════════════════ */

/* ── Active nav link detection ───────────────────────────────────────────────
   Python-side sets .active on labels via synapse-nav-link class.
   JS adds 'active-menu-link' on <a> elements for legacy compat.
   CSS neutralizes the old sidebar styles on .active-menu-link.
   ─────────────────────────────────────────────────────────────────────────── */

function updateActiveLinks() {
    const path = window.location.pathname;
    document.querySelectorAll('a[href]').forEach(a => {
        const href = a.getAttribute('href');
        if (href && href === path) {
            a.classList.add('active-menu-link');
            // Also mark child .synapse-nav-link label as active
            const navLabel = a.querySelector('.synapse-nav-link');
            if (navLabel) navLabel.classList.add('active');
        } else {
            a.classList.remove('active-menu-link');
            const navLabel = a.querySelector('.synapse-nav-link');
            if (navLabel && !navLabel.dataset.pyActive) {
                // Don't remove if Python set it active
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', updateActiveLinks);
updateActiveLinks();

const _synapseNavObserver = new MutationObserver(function(mutations) {
    const hasLinks = mutations.some(m =>
        [...m.addedNodes].some(n =>
            n.nodeName === 'A' || (n.querySelectorAll && n.querySelectorAll('a').length > 0)
        )
    );
    if (hasLinks) updateActiveLinks();
});
_synapseNavObserver.observe(document.body, { childList: true, subtree: true });


/* ── Dark Minimal Mode — OLED night reading ──────────────────────────────── */

(function () {
    if (localStorage.getItem('synapse_minimal') === '1') {
        document.documentElement.classList.add('synapse-minimal-pending');
        document.addEventListener('DOMContentLoaded', function () {
            document.body.classList.add('synapse-minimal');
            document.documentElement.classList.remove('synapse-minimal-pending');
        });
    }
})();

function toggleMinimalMode() {
    const active = document.body.classList.toggle('synapse-minimal');
    localStorage.setItem('synapse_minimal', active ? '1' : '0');
    return active;
}


/* ── Confetti célébration — 0 urgences ───────────────────────────────────── */

function synapseConfetti() {
    const colors = ['#4338CA', '#6366F1', '#16A34A', '#F59E0B', '#0EA5E9'];
    for (let i = 0; i < 52; i++) {
        const el = document.createElement('div');
        const size = 5 + Math.random() * 7;
        const isCircle = Math.random() > 0.5;
        el.style.cssText = [
            'position:fixed',
            `left:${15 + Math.random() * 70}vw`,
            `top:${5 + Math.random() * 25}vh`,
            `width:${size}px`,
            `height:${size}px`,
            `background:${colors[Math.floor(Math.random() * colors.length)]}`,
            `border-radius:${isCircle ? '50%' : '2px'}`,
            'z-index:99999',
            'pointer-events:none',
            'opacity:1',
            `transform:rotate(${Math.random() * 360}deg)`,
            'transition:transform 1.3s cubic-bezier(0.2,0,0.8,1), top 1.3s cubic-bezier(0.2,0,0.8,1), opacity 1.3s ease-out',
        ].join(';');
        document.body.appendChild(el);
        requestAnimationFrame(() => {
            el.style.top = `${55 + Math.random() * 45}vh`;
            el.style.transform = `rotate(${Math.random() * 720}deg) scale(0.2)`;
            el.style.opacity = '0';
        });
        setTimeout(() => el.remove(), 1500);
    }
}


/* ── Apply display font to date heading ──────────────────────────────────── */

function applyDisplayFont() {
    // Apply Plus Jakarta Sans to headings that have .synapse-display class
    const els = document.querySelectorAll('.synapse-display');
    els.forEach(el => {
        el.style.fontFamily = "'Plus Jakarta Sans', -apple-system, sans-serif";
    });
}

document.addEventListener('DOMContentLoaded', applyDisplayFont);
