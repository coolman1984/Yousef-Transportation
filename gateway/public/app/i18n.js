/* Driver page texts. Arabic first; the driver can switch to English. */
(function () {
  'use strict';
  var D = window.D = window.D || {};
  var dict = {
    ar: {
      title: 'أمر التشغيل', trip: 'مشوارك', start: 'البداية', road: 'في الطريق', end: 'النهاية', paper: 'الورقة', done: 'تم',
      no: 'رقم الأمر', date: 'التاريخ', car: 'السيارة', dest: 'الوجهة', stops: 'المحطات', pax: 'الركاب', driver: 'السائق',
      begin: 'ابدأ المشوار', begin_hint: 'هتصوّر عداد الكيلومترات وتكتب الرقم. ده بياخد نص دقيقة.',
      odo_start: 'صوّر عداد البداية', odo_end: 'صوّر عداد النهاية', retake: 'صوّر تاني', km_start: 'قراءة العداد عند البداية', km_end: 'قراءة العداد عند النهاية',
      km_hint: 'اكتب الرقم زي ما هو ظاهر في العداد.', confirm_start: 'ابدأ', confirm_end: 'أنهِ المشوار',
      running: 'المشوار شغّال', since: 'من الساعة', elapsed: 'مدة المشوار', finish: 'أنهِ المشوار', note: 'أضف ملاحظة', note_ph: 'اكتب ملاحظتك', send: 'ابعت',
      route: 'خط السير الفعلي', route_hint: 'لو غيّرت المسار، اكتبه هنا. لو لأ سيبه زي ما هو.',
      paper_t: 'صوّر الورقة الموقّعة', paper_hint: 'الورقة بتوقيع الراكب وتوقيعك. صوّرها واضحة.', skip_paper: 'هصوّرها بعدين', paper_missing: 'لسه ما صوّرتش الورقة الموقّعة.',
      thanks: 'تسلم إيدك!', thanks_b: 'المشوار اتسجّل. لو لسه فيه حاجة ما وصلتش، هتتبعت لوحدها أول ما الشبكة ترجع.',
      saved_here: 'اتحفظ على موبايلك', received: 'وصل للمكتب', waiting: 'مستني شبكة', failed: 'تعذّر الإرسال — دوس لإعادة المحاولة',
      offline: 'مفيش شبكة دلوقتي. كمّل شغلك، كل حاجة بتتحفظ وهتتبعت لوحدها.', sending: 'بيتبعت…', all_sent: 'كل حاجة وصلت للمكتب',
      n_waiting: 'فيه {n} حاجة مستنية الإرسال', retry: 'حاول تاني',
      cancelled: 'المشوار ده اتلغى', cancelled_b: 'كلّم المكتب لو دي غلطة.', expired: 'اللينك ده انتهت صلاحيته', expired_b: 'اطلب لينك جديد من المكتب.', unknown: 'اللينك ده مش شغّال', unknown_b: 'اتأكد إنك فتحت اللينك كامل، أو اطلب لينك جديد من المكتب.',
      second: 'المشوار ده مفتوح على موبايل تاني', second_b: 'تقدر تكمّل، بس المكتب هيراجع اللي بتبعته.',
      end_low: 'عداد النهاية أقل من عداد البداية. اتأكد من الرقم.', end_low_send: 'الرقم صح، ابعت', check_km: 'اتأكد من الرقم',
      km_required: 'اكتب قراءة العداد', photo_required: 'صوّر العداد الأول', photo_ok: 'الصورة اتحفظت',
      cam_take: 'التقط', cam_cancel: 'إلغاء', cam_gallery: 'اختار من المعرض', cam_denied: 'مقدرناش نفتح الكاميرا. تقدر تختار صورة.',
      skip_photo: 'كمّل من غير صورة', pax_none: 'مفيش ركاب مسجّلين', kmu: 'كم',
      lang: 'English', contrast: 'وضوح أعلى', stamp: 'الصورة هتتختم برقم الأمر والوقت.', back: 'رجوع', next: 'التالي',
      new_version: 'المشوار اتحدّث من المكتب', loading: 'ثواني…', tryagain: 'حاول تاني', server_time_off: 'ساعة موبايلك مختلفة عن الساعة الفعلية. اظبطها من إعدادات الموبايل.',
    },
    en: {
      title: 'Trip order', trip: 'Your trip', start: 'Start', road: 'On the road', end: 'End', paper: 'Paper', done: 'Done',
      no: 'Order no.', date: 'Date', car: 'Car', dest: 'Destination', stops: 'Stops', pax: 'Passengers', driver: 'Driver',
      begin: 'Start the trip', begin_hint: 'You will photograph the odometer and type the number. It takes half a minute.',
      odo_start: 'Photograph the start odometer', odo_end: 'Photograph the end odometer', retake: 'Take again', km_start: 'Odometer reading at the start', km_end: 'Odometer reading at the end',
      km_hint: 'Type the number exactly as the odometer shows it.', confirm_start: 'Start', confirm_end: 'End the trip',
      running: 'Trip in progress', since: 'Since', elapsed: 'Trip time', finish: 'End the trip', note: 'Add a note', note_ph: 'Write your note', send: 'Send',
      route: 'Route actually taken', route_hint: 'If the route changed, write it here. If not, leave it as it is.',
      paper_t: 'Photograph the signed paper', paper_hint: 'The paper with the passenger\'s signature and yours. Take it clearly.', skip_paper: 'I will photograph it later', paper_missing: 'The signed paper has not been photographed yet.',
      thanks: 'Well done!', thanks_b: 'The trip is recorded. Anything that has not arrived yet will be sent by itself when the network is back.',
      saved_here: 'Saved on your phone', received: 'Received by the office', waiting: 'Waiting for network', failed: 'Could not send - tap to retry',
      offline: 'No network right now. Keep going: everything is saved and will be sent by itself.', sending: 'Sending…', all_sent: 'Everything reached the office',
      n_waiting: '{n} item(s) waiting to be sent', retry: 'Try again',
      cancelled: 'This trip was cancelled', cancelled_b: 'Call the office if this is a mistake.', expired: 'This link has expired', expired_b: 'Ask the office for a new link.', unknown: 'This link does not work', unknown_b: 'Make sure you opened the whole link, or ask the office for a new one.',
      second: 'This trip is open on another phone', second_b: 'You can continue, but the office will review what you send.',
      end_low: 'The end reading is lower than the start reading. Check the number.', end_low_send: 'The number is right, send', check_km: 'Check the number',
      km_required: 'Type the odometer reading', photo_required: 'Photograph the odometer first', photo_ok: 'Photo saved',
      cam_take: 'Capture', cam_cancel: 'Cancel', cam_gallery: 'Choose from gallery', cam_denied: 'The camera could not be opened. You can choose a photo.',
      skip_photo: 'Continue without a photo', pax_none: 'No passengers listed', kmu: 'km',
      lang: 'العربية', contrast: 'Higher contrast', stamp: 'The photo is stamped with the order number and time.', back: 'Back', next: 'Next',
      new_version: 'The trip was updated by the office', loading: 'One moment…', tryagain: 'Try again', server_time_off: 'Your phone clock is different from the real time. Fix it in the phone settings.',
    },
  };
  D.lang = 'ar';
  try { var s = localStorage.getItem('to.lang'); if (s === 'ar' || s === 'en') D.lang = s; else if ((navigator.language || '').toLowerCase().indexOf('ar') !== 0 && /^en/i.test(navigator.language || '')) D.lang = 'en'; } catch (e) { /* private mode */ }
  D.t = function (k, v) {
    var s = (dict[D.lang] || {})[k]; if (s === undefined) s = dict.en[k]; if (s === undefined) return k;
    if (v) s = s.replace(/\{(\w+)\}/g, function (m, n) { return v[n] === undefined ? m : v[n]; });
    return s;
  };
  D.setLang = function (l) {
    D.lang = l === 'en' ? 'en' : 'ar';
    try { localStorage.setItem('to.lang', D.lang); } catch (e) { /* ignore */ }
    document.documentElement.lang = D.lang; document.documentElement.dir = D.lang === 'ar' ? 'rtl' : 'ltr';
  };
  D.setLang(D.lang);
  D.esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  D.digits = function (s) { return String(s).replace(/[٠-٩]/g, function (d) { return d.charCodeAt(0) - 1632; }).replace(/[۰-۹]/g, function (d) { return d.charCodeAt(0) - 1776; }); };
})();
