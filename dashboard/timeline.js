/**
 * UNITARES Dashboard — Skeletons & WS Status
 *
 * Skeleton loaders for panels, WebSocket status label.
 * (Activity timeline removed — duplicated Agents list.)
 */
(function () {
    'use strict';

    if (typeof DashboardState === 'undefined') {
        console.warn('[TimelineModule] state.js not loaded, module disabled');
        return;
    }

    // ========================================================================
    // Skeleton loader initialization
    // ========================================================================

    function initSkeletons() {
        if (typeof LoadingSkeleton === 'undefined') return;
        var targets = {
            'agents-skeleton': { type: 'listItem', count: 3 },
            'discoveries-skeleton': { type: 'card', count: 3 },
            'dialectic-skeleton': { type: 'card', count: 2 }
        };
        var ids = Object.keys(targets);
        for (var i = 0; i < ids.length; i++) {
            var el = document.getElementById(ids[i]);
            if (el) {
                el.innerHTML = LoadingSkeleton.create(targets[ids[i]].type, targets[ids[i]].count);
            }
        }
    }

    initSkeletons();

    // ========================================================================
    // WebSocket status label
    // ========================================================================

    function updateWSStatusLabel(status) {
        var dot = document.querySelector('#ws-status .ws-dot');
        var label = document.querySelector('#ws-status .ws-label');
        var container = document.getElementById('ws-status');
        if (!dot || !label || !container) return;

        dot.className = 'ws-dot ' + status;
        var labels = { connected: 'Live', polling: 'Polling', reconnecting: 'Reconnecting', disconnected: 'Offline' };
        label.textContent = labels[status] || 'Offline';
        var titles = { connected: 'Connected via WebSocket', polling: 'Polling (WebSocket unavailable)', reconnecting: 'Reconnecting...', disconnected: 'Offline' };
        container.title = titles[status] || 'Offline';
    }

    // ========================================================================
    // Public API
    // ========================================================================

    window.TimelineModule = {
        initSkeletons: initSkeletons,
        updateWSStatusLabel: updateWSStatusLabel
    };
})();
