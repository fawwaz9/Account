import { useAuth } from "../../../app/auth/AuthContext";
import { KindColors } from "../kindColors";

/** The student's per-kind colour overrides, read from the signed-in user. */
export function useKindColors(): KindColors {
  return useAuth().user?.preferences?.event_colors ?? {};
}
