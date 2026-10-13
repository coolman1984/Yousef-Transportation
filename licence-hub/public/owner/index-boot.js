import { loadPending, loadUndelivered } from '/owner/app.js';

const root = document.getElementById('root');
loadUndelivered(root);
loadPending(root);
