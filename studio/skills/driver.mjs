// Driver skills on the phone page (the real driver page served by the real mailbox code); each proves its result in the office.
function must(cond, msg) { if (!cond) throw new Error('proof failed: ' + msg); }
const css = (s) => 'css:' + s;

async function shoot(stage, reading) {
  await stage.page.evaluate((v) => { window.__odo = v; }, String(reading));
  await stage.click(css('[data-a="shoot"]'), { expect: () => document.querySelector('.cam video') && document.querySelector('.cam video').videoWidth > 0 });
  await stage.pause(900);
  await stage.click(css('.cam [data-s]'), { expect: () => document.querySelector('.photo img') });
}

async function pulled(set, trip, check, what) {
  for (let i = 0; i < 40; i++) {
    await set.api.post('/api/gateway/pull');
    const st = await set.api.get('/api/state');
    const t = st.trips.find((x) => x.id === trip.id);
    if (check(t, st)) return { t, st };
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error('proof failed: ' + what);
}

export async function openLink(stage, set, link) {
  await stage.page.goto(link, { waitFor: () => document.querySelector('[data-a="begin"]') });
  const no = await stage.page.evaluate(() => document.querySelector('.top .no').textContent);
  stage.mark('phone-card', { no });
  return no;
}

export async function startTrip(stage, set, trip) {
  await stage.click(css('[data-a="begin"]'), { expect: () => document.querySelector('[data-a="shoot"]') });
  await shoot(stage, set.actor.startKm);
  await stage.fill('قراءة العداد عند البداية', String(set.actor.startKm));
  await stage.click(css('[data-a="start"]'), { expect: () => document.querySelector('[data-a="finish"]') });
  await stage.page.waitFor(() => document.querySelector('.sync.ok'), { what: '✓✓ received' });
  const { t, st } = await pulled(set, trip, (x) => x.status === 'started', 'the office sees the start');
  must(t.startKm === set.actor.startKm && st.tripPhotos.some((p) => p.tripId === trip.id && p.kind === 'start_odo'), 'start reading and photo arrived');
  stage.mark('started', { startKm: t.startKm, startAt: t.startAt });
  return t;
}

export async function endTrip(stage, set, trip) {
  await stage.click(css('[data-a="finish"]'), { expect: () => document.querySelector('[data-a="end"]') });
  await shoot(stage, set.actor.endKm);
  await stage.fill('قراءة العداد عند النهاية', String(set.actor.endKm));
  await stage.click(css('[data-a="end"]'), { expect: () => document.querySelector('[data-a="skip-paper"]') });
  await shoot(stage, 'paper');
  await stage.click(css('[data-a="paper"]'), { expect: () => document.querySelector('.big-ok') });
  await stage.page.waitFor(() => document.querySelector('.sync.ok'), { what: '✓✓ received' });
  const { t, st } = await pulled(set, trip, (x, s) => x.status === 'finished' && s.tripPhotos.filter((p) => p.tripId === trip.id).length === 3, 'the office sees the end and three photos');
  must(t.endKm === set.actor.endKm, 'end reading arrived');
  stage.mark('ended', { endKm: t.endKm, endAt: t.endAt });
  return t;
}
