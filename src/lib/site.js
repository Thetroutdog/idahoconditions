// One place for site-wide constants. Change here, not in pages.
export const SITE = {
  name: 'Idaho Conditions',
  url: 'https://idahoconditions.com',
  contactEmail: 'contact@idahoconditions.com',
  x: 'https://x.com/idahoconditions',
  instagram: 'https://www.instagram.com/idahoconditions/',
  // beehiiv subscribe form: the data-beehiiv-form id from beehiiv's "Embed" script (public, not a secret).
  // While empty, the Brief section shows "Signup opens soon" instead of a form.
  beehiivFormId: '39bde035-482c-48e1-b046-4a5bf2cbe0b8',
  beehiivArchive: '',
};

// Date shown at the bottom of the Terms and Privacy pages. Bump it whenever either page changes in substance.
export const LEGAL_UPDATED = 'November 23, 2026';

// Required credit wording from the Idaho Transportation Department (Idaho 511). Use it as written wherever 511 data is credited.
export const ITD_CREDIT = 'Source: Idaho Transportation Department (ITD) / Idaho 511';
export const ITD_URL = 'https://511.idaho.gov/';

// Short reminders shown beside the data they apply to. The full text is on the Terms page.
export const NOTES = {
  general: 'Informational only. Conditions change fast and data can be late or wrong. Check the official source before you go.',
  roads: 'Road information comes from Idaho 511 and can lag. Check 511 before you drive.',
  rivers: 'Flows are provisional gauge readings, not flood or safety forecasts.',
  avalanche: 'We link to avalanche center forecasts but do not publish or summarize danger ratings. Read your center\u2019s current forecast before entering avalanche terrain.',
  fire: 'Fire points are not evacuation or closure notices. Follow local officials.',
};

// Feedback line shown under the Brief signup on the home page and under the live readings on region pages.
export const feedbackMailto = (topic) => `mailto:${SITE.contactEmail}?subject=${encodeURIComponent(topic ? `Idaho Conditions: ${topic}` : 'Idaho Conditions feedback')}`;

