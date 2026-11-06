'use client';

import { RoleFamily } from '../../lib/api';
import ListField from './list-field';

export type RoleMode = 'all' | 'specific';

export default function RolePicker({
  families,
  mode,
  onModeChange,
  selected,
  onSelectedChange,
  keywords,
  onKeywordsChange,
}: {
  families: RoleFamily[];
  mode: RoleMode;
  onModeChange: (mode: RoleMode) => void;
  selected: string[];
  onSelectedChange: (keys: string[]) => void;
  keywords: string[];
  onKeywordsChange: (keywords: string[]) => void;
}) {
  function toggle(key: string) {
    onSelectedChange(selected.includes(key) ? selected.filter((item) => item !== key) : [...selected, key]);
  }

  return (
    <div className="role-picker">
      <label className="choice-row">
        <input type="radio" name="role-mode" checked={mode === 'all'} onChange={() => onModeChange('all')} />
        <span><strong>Every tech role</strong><small>Engineering, data, DevOps, design, product, QA, security, support and more. Best way to start wide.</small></span>
      </label>
      <label className="choice-row">
        <input type="radio" name="role-mode" checked={mode === 'specific'} onChange={() => onModeChange('specific')} />
        <span><strong>Only these types</strong><small>Pick the kinds of roles you want to see.</small></span>
      </label>
      {mode === 'specific' && (
        <div className="role-grid">
          {families.map((family) => (
            <label className={`role-option${selected.includes(family.key) ? ' selected' : ''}`} key={family.key}>
              <input type="checkbox" checked={selected.includes(family.key)} onChange={() => toggle(family.key)} />
              {family.label}
            </label>
          ))}
        </div>
      )}
      <label className="field-label">Extra job-title words <span className="optional">(optional)</span>
        <ListField value={keywords} onChange={onKeywordsChange} rows={2} placeholder="e.g. recruiter, technical sourcer" />
        <small className="hint">Any job whose title contains one of these words also counts as a match.</small>
      </label>
    </div>
  );
}
