import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import HelpTip from "../../../shared/components/HelpTip";
import {
  ReviewCourse, TermReviewAnswers, TermReviews, fetchTermReviews, removeTermReview, saveTermReview,
  skipTermReview,
} from "../termReviews";

interface Props {
  readonly userId: string;
}

const SCALE = [1, 2, 3, 4, 5];

/**
 * "Rate your term" (Phase 2 item 13, D25): four questions about each course
 * that finished recently, and an opt-in to add your grade to the course's
 * distribution. Silent when no course is in its asking window.
 *
 * Nothing here ever shows a count. Grades opted in are counted daily into a
 * table no request can read, and only for a course with enough contributors;
 * the distributions are a later phase's.
 */
export default function TermReviewPanel({ userId }: Props) {
  const [data, setData] = useState<TermReviews | null>(null);
  const [open, setOpen] = useState(false);

  async function load() {
    try {
      setData(await fetchTermReviews(userId));
    } catch {
      setData(null);
    }
  }

  useEffect(() => { void load(); }, [userId]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!data || data.courses.length === 0) return null;
  const terms = [...new Set(data.courses.map((c) => c.term_label))].join(", ");

  return (
    <section className="termReviewPanel" aria-label="Rate your term">
      <div className="termReviewHeading">
        <h2>Rate your term</h2>
        <HelpTip label="About term reviews">
          Four quick questions about each course you just finished, and the choice to add your grade to
          the course&rsquo;s distribution. Grades are counted with no name attached, only once enough
          people have added theirs, and nothing is shown yet. You can take your grade back out at any time.
        </HelpTip>
      </div>
      <p className="small-text">
        {data.pending > 0
          ? `${data.pending} ${data.pending === 1 ? "course" : "courses"} from ${terms} to rate.`
          : `You've rated ${terms}. You can still change your answers for a while.`}
      </p>
      <button type="button" className="calButton" onClick={() => setOpen(true)}>
        {data.pending > 0 ? "Rate them" : "See your answers"}
      </button>
      {open && (
        <Modal title="Rate your term" onClose={() => setOpen(false)} panelClassName="widePopup">
          <div className="termReviewList">
            {data.courses.map((course) => (
              <ReviewForm key={course.course_id} userId={userId} course={course} onChanged={load} />
            ))}
          </div>
          <div className="calFormActions">
            <button type="button" className="calButton" onClick={() => setOpen(false)}>Done</button>
          </div>
        </Modal>
      )}
    </section>
  );
}

function blank(course: ReviewCourse): TermReviewAnswers {
  const review = course.review;
  return {
    hours_per_week: review?.hours_per_week ?? null,
    difficulty: review?.difficulty ?? null,
    clarity: review?.clarity ?? null,
    would_take_again: review?.would_take_again ?? null,
    contribute_grade: review?.contribute_grade ?? false,
  };
}

interface FormProps {
  readonly userId: string;
  readonly course: ReviewCourse;
  readonly onChanged: () => Promise<void>;
}

function ReviewForm({ userId, course, onChanged }: FormProps) {
  const [answers, setAnswers] = useState<TermReviewAnswers>(() => blank(course));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const review = course.review;
  const locked = Boolean(review && !review.skipped && !review.answers_editable);
  const canContribute = course.has_grade && course.can_contribute;

  function set<K extends keyof TermReviewAnswers>(key: K, value: TermReviewAnswers[K]) {
    setAnswers((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  async function act(step: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await step();
      await onChanged();
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const question = `${course.code} — ${course.name}`;

  return (
    <fieldset className="termReviewForm" aria-label={question}>
      <legend>{course.code} <span className="small-text muted">{course.name} · {course.term_label}</span></legend>
      {review?.skipped ? (
        <p className="small-text muted">Skipped. You can still answer below.</p>
      ) : null}
      {locked && (
        <p className="small-text muted">Your answers have locked. You can still change whether your grade is added.</p>
      )}

      <label className="termReviewField">
        <span>Hours a week, outside class</span>
        <input type="number" min={0} max={80} disabled={locked} aria-label={`Hours a week for ${course.code}`}
               value={answers.hours_per_week ?? ""}
               onChange={(e) => set("hours_per_week", e.target.value === "" ? null : Number(e.target.value))} />
      </label>

      {(["difficulty", "clarity"] as const).map((key) => (
        <div key={key} className="termReviewField" role="group"
             aria-label={`${key === "difficulty" ? "Difficulty" : "Instructor clarity"} of ${course.code}`}>
          <span>{key === "difficulty" ? "Difficulty (1 easy, 5 hard)" : "Instructor clarity (1 unclear, 5 clear)"}</span>
          <span className="termReviewScale">
            {SCALE.map((n) => (
              <button key={n} type="button" disabled={locked} aria-pressed={answers[key] === n}
                      className={answers[key] === n ? "calViewTab calViewTabActive" : "calViewTab"}
                      onClick={() => set(key, answers[key] === n ? null : n)}>
                {n}
              </button>
            ))}
          </span>
        </div>
      ))}

      <div className="termReviewField" role="group" aria-label={`Would take ${course.code} again`}>
        <span>Would you take it again?</span>
        <span className="termReviewScale">
          {([true, false] as const).map((value) => (
            <button key={String(value)} type="button" disabled={locked} aria-pressed={answers.would_take_again === value}
                    className={answers.would_take_again === value ? "calViewTab calViewTabActive" : "calViewTab"}
                    onClick={() => set("would_take_again", answers.would_take_again === value ? null : value)}>
              {value ? "Yes" : "No"}
            </button>
          ))}
        </span>
      </div>

      <label className="termReviewContribute">
        <input type="checkbox" checked={answers.contribute_grade} disabled={!canContribute}
               onChange={(e) => set("contribute_grade", e.target.checked)} />
        <span>
          Add my final grade to {course.code}&rsquo;s distribution, with no name attached
          {!canContribute && (
            <span className="small-text muted">
              {" "}— {course.has_grade ? "this course can't be matched to a course and term to count it under" : "there's no grade recorded for it yet"}
            </span>
          )}
        </span>
      </label>

      {error && <p className="small-text error" role="alert">{error}</p>}
      {saved && !error && <p className="small-text" role="status">Saved.</p>}

      <div className="catalogueActions">
        <button type="button" className="calButton calButtonPrimary" disabled={busy}
                onClick={() => void act(() => saveTermReview(userId, course.course_id, answers))}>
          Save
        </button>
        {!review && (
          <button type="button" className="calButton" disabled={busy}
                  onClick={() => void act(() => skipTermReview(userId, course.course_id))}>
            Skip this course
          </button>
        )}
        {review && !review.skipped && (deleting ? (
          <>
            <span className="small-text">Delete your answers{review.contribute_grade ? " and take your grade out" : ""}?</span>
            <button type="button" className="calButton calButtonDanger" disabled={busy}
                    onClick={() => void act(async () => {
                      await removeTermReview(userId, course.course_id);
                      setDeleting(false);
                      setAnswers({ hours_per_week: null, difficulty: null, clarity: null,
                                   would_take_again: null, contribute_grade: false });
                    })}>
              Yes, delete
            </button>
            <button type="button" className="calButton" onClick={() => setDeleting(false)}>Keep</button>
          </>
        ) : (
          <button type="button" className="courseLinkAdd" onClick={() => setDeleting(true)}>Delete my review</button>
        ))}
      </div>
    </fieldset>
  );
}
