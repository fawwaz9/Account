import { useAuth } from "../../../app/auth/AuthContext";
import { KindColors } from "../kindColors";

/**
 * The student's chosen colour per event kind -- only the ones they changed.
 *
 * Read from the signed-in user rather than fetched: Settings calls
 * `refreshUser()` after saving, so a new colour reaches every chip with no
 * request of its own.
 */
export function useKindColors(): KindColors {
  return useAuth().user?.preferences?.event_colors ?? {};
}
