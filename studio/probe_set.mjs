import { buildSet } from './sets/film1.mjs';
const s = await buildSet({ root: new URL('./takes/_probe', import.meta.url).pathname });
const st = await s.api.get('/api/state'); const ins = await s.api.get('/api/insights');
console.log('trips', st.trips.length, 'today', st.trips.filter((t) => t.date === '2026-10-06').map((t) => [t.no, t.status, ins[t.id].trust, ins[t.id].reasons.join(',')]));
console.log('clock', s.clock.now().toISOString(), 'actor', s.actor.startKm, s.actor.endKm);
await s.stop();
