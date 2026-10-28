import { CourseLink } from "../types";

/** The course's links, and the handler that opens the editor. */
interface CourseLinksProps {
  readonly links: readonly CourseLink[];
  readonly onEdit: () => void;
}

/** True for an http or https URL, the only kind ever rendered as a link. */
function isSafe(url: string): boolean {
  const scheme = url.slice(0, url.indexOf(":")).toLowerCase();
  return scheme === "http" || scheme === "https";
}

/** A course's resource links, http and https only, with a button to add or edit them. */
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
