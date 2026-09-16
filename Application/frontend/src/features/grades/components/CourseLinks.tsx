import { CourseLink } from "../types";

interface CourseLinksProps {
  readonly links: readonly CourseLink[];
  readonly onEdit: () => void;
}

/**
 * Only http(s) is ever rendered as an anchor.
 *
 * The API refuses anything else, so this is the second lock on the same door --
 * worth having because it is the client that turns a stored string into
 * something clickable, and a row written before that check existed would
 * otherwise still be live.
 */
function isSafe(url: string): boolean {
  const scheme = url.slice(0, url.indexOf(":")).toLowerCase();
  return scheme === "http" || scheme === "https";
}

/**
 * Where a course lives: Canvas, Piazza, a syllabus.
 *
 * Above "What this cost" rather than inside it, deliberately. `CourseCost`
 * returns null when the course has cost nothing, so a control living there
 * would vanish on exactly the courses whose links you most want -- the same
 * fault the budget page had, where both of its controls disappeared in the
 * month you were most likely to be setting categories up.
 */
export default function CourseLinks({ links, onEdit }: CourseLinksProps) {
  const safe = links.filter((link) => isSafe(link.url));

  return (
    <div className="courseLinks">
      {safe.map((link) => (
        <a
          key={`${link.title}-${link.url}`}
          className="courseLink"
          href={link.url}
          target="_blank"
          // noopener stops the opened page reaching back through window.opener;
          // noreferrer keeps the course page out of its referer log.
          rel="noopener noreferrer"
        >
          {link.title}
        </a>
      ))}

      <button type="button" className="courseLinkAdd" onClick={onEdit}>
        {safe.length > 0 ? "Edit links" : "Add resource link"}
      </button>
    </div>
  );
}
