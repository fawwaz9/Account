import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Modal from "../../shared/components/Modal";
import { isTypingContext } from "../../shared/hooks/useShortcut";
import { NAV } from "./Sidebar";

/** How long after G the second key still counts. */
export const SEQUENCE_MS = 1500;

/**
 * Global shortcuts: G then a letter navigates, ? opens the list.
 * Listens in the capture phase so the key after G never reaches a page.
 */
export default function KeyboardShortcuts() {
  const navigate = useNavigate();
  const [listOpen, setListOpen] = useState(false);
  const armedUntil = useRef(0);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isTypingContext(event)) {
        armedUntil.current = 0;
        return;
      }
      const key = event.key.toLowerCase();

      if (armedUntil.current > Date.now()) {
        armedUntil.current = 0;
        const item = NAV.find((entry) => entry.key === key);
        if (item) {
          event.preventDefault();
          navigate(item.to);
        }
        return;
      }

      if (key === "g") {
        event.preventDefault();
        armedUntil.current = Date.now() + SEQUENCE_MS;
      } else if (event.key === "?") {
        event.preventDefault();
        setListOpen(true);
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [navigate]);

  if (!listOpen) return null;

  return (
    <Modal title="Keyboard shortcuts" onClose={() => setListOpen(false)}>
      <dl className="shortcutList">
        {NAV.map((item) => (
          <div key={item.to} className="shortcutRow">
            <dt><kbd>G</kbd> <kbd>{item.key.toUpperCase()}</kbd></dt>
            <dd>{item.label}</dd>
          </div>
        ))}
        <div className="shortcutRow">
          <dt><kbd>N</kbd></dt>
          <dd>New item on this page: event, task, job, course, or money</dd>
        </div>
        <div className="shortcutRow">
          <dt><kbd>←</kbd> <kbd>→</kbd></dt>
          <dd>Calendar: previous or next week or month</dd>
        </div>
        <div className="shortcutRow">
          <dt><kbd>T</kbd></dt>
          <dd>Calendar: today</dd>
        </div>
        <div className="shortcutRow">
          <dt><kbd>Ctrl</kbd> <kbd>K</kbd></dt>
          <dd>Quick add, from anywhere</dd>
        </div>
        <div className="shortcutRow">
          <dt><kbd>?</kbd></dt>
          <dd>This list</dd>
        </div>
      </dl>
      <div className="shortcutActions">
        <button type="button" className="buttons" onClick={() => setListOpen(false)}>
          Close
        </button>
      </div>
    </Modal>
  );
}
