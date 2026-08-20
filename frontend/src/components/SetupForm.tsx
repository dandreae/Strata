import { useRef, useState, type DragEvent } from "react";
import type { Objective } from "../lib/api";
import { validateForm } from "../lib/validate";

export interface SetupValues {
  file: File;
  quantity: number;
  maxPrintMinutes: number;
  maxMaterialGrams: number;
  objective: Objective;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function SetupForm({ disabled, onSubmit }: { disabled: boolean; onSubmit: (values: SetupValues) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [quantity, setQuantity] = useState(100);
  const [maxPrintMinutes, setMaxPrintMinutes] = useState(180);
  const [maxMaterialGrams, setMaxMaterialGrams] = useState(80);
  const [objective, setObjective] = useState<Objective>("balanced");
  const [errors, setErrors] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function pickFile(candidate: File | null | undefined) {
    if (candidate) setFile(candidate);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragOver(false);
    if (disabled) return;
    pickFile(event.dataTransfer.files?.[0]);
  }

  function handleSubmit() {
    const validationErrors = validateForm({
      file,
      productionQuantity: quantity,
      maxPrintTimeMinutes: maxPrintMinutes,
      maxFilamentGrams: maxMaterialGrams,
    });
    setErrors(validationErrors);
    if (validationErrors.length > 0 || !file) return;
    onSubmit({ file, quantity, maxPrintMinutes, maxMaterialGrams, objective });
  }

  return (
    <section className="setup-card">
      <p className="setup-intro">
        Strata autonomously searches manufacturing configurations for you — an agent proposes layer
        height, infill, and wall count combinations worth testing, measures each one with a real
        slicer, and recommends a winner. You state the outcome you want; you don't tune slicer settings.
      </p>

      <div
        className={`dropzone ${isDragOver ? "dropzone-active" : ""} ${file ? "dropzone-filled" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !disabled && fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
        }}
        aria-label="Upload STL file"
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".stl"
          disabled={disabled}
          className="dropzone-input"
          onChange={(e) => pickFile(e.target.files?.[0])}
        />
        {file ? (
          <div className="dropzone-file">
            <span className="dropzone-file-icon" aria-hidden="true">
              ▲
            </span>
            <div>
              <p className="dropzone-filename">{file.name}</p>
              <p className="dropzone-filesize">{formatFileSize(file.size)} · click or drop to replace</p>
            </div>
          </div>
        ) : (
          <div className="dropzone-empty">
            <span className="dropzone-icon" aria-hidden="true">
              ▲
            </span>
            <p>Drag & drop an STL file, or click to browse</p>
          </div>
        )}
      </div>

      <div className="setup-grid">
        <label className="field">
          <span className="field-label">Production quantity</span>
          <input
            type="number"
            min={1}
            value={quantity}
            disabled={disabled}
            onChange={(e) => setQuantity(Number(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="field-label">Max print time (min/part)</span>
          <input
            type="number"
            min={0}
            step={1}
            value={maxPrintMinutes}
            disabled={disabled}
            onChange={(e) => setMaxPrintMinutes(Number(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="field-label">Max material (g/part)</span>
          <input
            type="number"
            min={0}
            step={0.1}
            value={maxMaterialGrams}
            disabled={disabled}
            onChange={(e) => setMaxMaterialGrams(Number(e.target.value))}
          />
        </label>

        <label className="field">
          <span className="field-label">Optimize for</span>
          <select value={objective} disabled={disabled} onChange={(e) => setObjective(e.target.value as Objective)}>
            <option value="balanced">Balanced</option>
            <option value="minimize_material">Minimize material</option>
            <option value="minimize_time">Minimize print time</option>
          </select>
        </label>
      </div>

      {errors.length > 0 && (
        <ul className="status status-error">
          {errors.map((msg, i) => (
            <li key={i}>{msg}</li>
          ))}
        </ul>
      )}

      <button type="button" className="cta-button" disabled={disabled} onClick={handleSubmit}>
        {disabled ? "Optimizing…" : "Optimize Part"}
      </button>
    </section>
  );
}
