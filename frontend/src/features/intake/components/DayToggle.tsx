interface DayToggleProps {
  done: boolean;
  saving: boolean;
  disabled: boolean;
  onToggle: () => void;
}

export default function DayToggle({
  done,
  saving,
  disabled,
  onToggle,
}: DayToggleProps) {
  return (
    <button
      type="button"
      className={`day-toggle${done ? " is-done" : ""}`}
      aria-pressed={done}
      disabled={disabled}
      onClick={onToggle}
    >
      <span className="day-toggle-switch" aria-hidden="true">
        <span />
      </span>
      <span className="day-toggle-copy">
        <strong>Day complete</strong>
        <span>
          {saving
            ? "Saving…"
            : done
              ? "Editing locked · tap to reopen"
              : "Tap to lock editing"}
        </span>
      </span>
    </button>
  );
}
