// ISO 3166 numeric (world-atlas feature ids) to alpha-2 (used throughout the data).
// Only countries that can appear in the data, plus EU members for the EU bloc.

export const NUMERIC_TO_ISO2: Record<string, string> = {
  "036": "AU", "040": "AT", "056": "BE", "076": "BR", "100": "BG", "112": "BY", "124": "CA",
  "156": "CN", "158": "TW", "188": "CR", "191": "HR", "196": "CY", "203": "CZ", "208": "DK",
  "233": "EE", "246": "FI", "250": "FR", "276": "DE", "300": "GR", "348": "HU", "356": "IN",
  "360": "ID", "372": "IE", "376": "IL", "380": "IT", "392": "JP", "410": "KR", "428": "LV",
  "440": "LT", "442": "LU", "458": "MY", "470": "MT", "484": "MX", "528": "NL", "608": "PH",
  "616": "PL", "620": "PT", "642": "RO", "702": "SG", "703": "SK", "704": "VN", "705": "SI",
  "710": "ZA", "724": "ES", "752": "SE", "756": "CH", "764": "TH", "826": "GB", "840": "US",
};

export const EU_MEMBERS = new Set([
  "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
  "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
]);

// Too small for the 1:110m atlas; drawn as a dot instead. [longitude, latitude]
export const POINT_COUNTRIES: Record<string, [number, number]> = {
  SG: [103.82, 1.35],
  TW: [120.97, 23.7], // in the atlas, but small enough to miss
};
