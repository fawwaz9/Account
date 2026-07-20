interface CourseSearchProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
}

export default function CourseSearch({ value, onChange }: CourseSearchProps) {
  return (
    <input
      className="search-courses"
      id="search-courses"
      placeholder="Search courses..."
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
