import { wireOffline, mountOfflineTier } from '/owner/app.js';

const card = document.querySelector('.card');
mountOfflineTier(card);
wireOffline(document.getElementById('offline-form'), document.getElementById('out'), card);
