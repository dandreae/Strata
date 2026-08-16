/**
 * Client-side form validation. This is a UX convenience only — the backend
 * (app/services/stl_validation.py, Pydantic field constraints) is the
 * authoritative validator and re-checks everything independently.
 */

export interface FormValues {
  file: File | null;
  productionQuantity: number;
  maxPrintTimeMinutes: number;
  maxFilamentGrams: number;
}

export function validateForm(values: FormValues): string[] {
  const errors: string[] = [];

  if (!values.file) {
    errors.push("Select an STL file to upload.");
  } else if (!values.file.name.toLowerCase().endsWith(".stl")) {
    errors.push("File must have a .stl extension.");
  }

  if (!Number.isFinite(values.productionQuantity) || values.productionQuantity < 1) {
    errors.push("Production quantity must be at least 1.");
  }

  if (!Number.isFinite(values.maxPrintTimeMinutes) || values.maxPrintTimeMinutes <= 0) {
    errors.push("Max print time must be a positive value.");
  }

  if (!Number.isFinite(values.maxFilamentGrams) || values.maxFilamentGrams <= 0) {
    errors.push("Max material must be a positive value.");
  }

  return errors;
}
