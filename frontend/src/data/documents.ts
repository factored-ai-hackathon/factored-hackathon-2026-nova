// Countries and document types exactly as the dataset has them (latam_raw.customers).
// The backend compares them ignoring case and accents.

export interface CountryOption {
  value: string; // as in the dataset
  flag: string;
  documentTypes: string[];
}

export const COUNTRIES: CountryOption[] = [
  { value: 'México', flag: '🇲🇽', documentTypes: ['DNI'] },
  { value: 'Colombia', flag: '🇨🇴', documentTypes: ['CC', 'CE', 'Pasaporte'] },
  { value: 'Argentina', flag: '🇦🇷', documentTypes: ['DNI'] },
];

export function documentTypesFor(country: string): string[] {
  return COUNTRIES.find((c) => c.value === country)?.documentTypes ?? [];
}
