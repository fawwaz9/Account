import { describe, expect, it } from "vitest";
import {
  bonusLast,
  carriesBonus,
  isAdditive,
  isOverMax,
  marksOver,
  scoringWeight,
} from "./bonus";
import { GradeCategory } from "./types";
import type { Course, CourseDetail, Grade } from "./types";

function grade(score: number | null, max_score: number): Pick<Grade, "score" | "max_score"> {
  return { score, max_score };
}

describe("isAdditive", () => {
  it("is true of bonus and nothing else", () => {
    expect(isAdditive(GradeCategory.BONUS)).toBe(true);

    for (const category of [
      GradeCategory.ASSIGNMENT,
      GradeCategory.LAB,
      GradeCategory.QUIZ,
      GradeCategory.MIDTERM,
      GradeCategory.PARTICIPATION,
      GradeCategory.PROJECT,
      GradeCategory.OTHER,
      GradeCategory.FINAL,
    ]) {
      expect(isAdditive(category)).toBe(false);
    }
  });

  it("takes a bare string, since weights arrive keyed by one", () => {
    expect(isAdditive("Bonus")).toBe(true);
    expect(isAdditive("Lab")).toBe(false);
  });
});

/**
 * The rule the whole module exists for: a course weighted 100 plus a 5 bonus is
 * still marked out of 100. Anything summing category weights has to come
 * through here rather than adding them raw, or the bonus silently becomes part
 * of the denominator and every average is diluted.
 */
describe("scoringWeight", () => {
  it("leaves bonus out of what the course is marked out of", () => {
    expect(
      scoringWeight({
        [GradeCategory.ASSIGNMENT]: 40,
        [GradeCategory.FINAL]: 60,
        [GradeCategory.BONUS]: 5,
      })
    ).toBe(100);
  });

  it("sums the ordinary categories", () => {
    expect(
      scoringWeight({ [GradeCategory.LAB]: 25, [GradeCategory.MIDTERM]: 35 })
    ).toBe(60);
  });

  it("is zero for nothing, and for bonus alone", () => {
    expect(scoringWeight({})).toBe(0);
    expect(scoringWeight({ [GradeCategory.BONUS]: 10 })).toBe(0);
  });
});

describe("isOverMax", () => {
  it("is true only when a score beats its own maximum", () => {
    expect(isOverMax(grade(11, 10))).toBe(true);
    expect(isOverMax(grade(10, 10))).toBe(false);
    expect(isOverMax(grade(9, 10))).toBe(false);
  });

  /**
   * An unmarked item is not a zero and is not bonus either -- it is nothing
   * yet, and the whole gradebook depends on that distinction.
   */
  it("is false for an unmarked item", () => {
    expect(isOverMax(grade(null, 10))).toBe(false);
  });

  it("is false when the maximum is zero, which divides nothing", () => {
    expect(isOverMax(grade(5, 0))).toBe(false);
  });
});

describe("marksOver", () => {
  it("reports how far over, rounded to cents", () => {
    expect(marksOver(grade(11, 10))).toBe(1);
    expect(marksOver(grade(10.505, 10))).toBe(0.51);
  });

  it("is zero when nothing went over", () => {
    expect(marksOver(grade(9, 10))).toBe(0);
    expect(marksOver(grade(null, 10))).toBe(0);
  });
});

/**
 * Two mechanisms reach the same place and the badge must not care which: an
 * explicit bonus category carrying weight, or an ordinary grade marked above
 * its own maximum.
 */
describe("carriesBonus", () => {
  const plain = { category_weights: { [GradeCategory.LAB]: 100 } } as unknown as Course;
  const weighted = {
    category_weights: { [GradeCategory.LAB]: 100, [GradeCategory.BONUS]: 5 },
  } as unknown as Course;

  it("is true for a weighted bonus category", () => {
    expect(carriesBonus(weighted)).toBe(true);
  });

  it("is false for a bonus category weighted zero", () => {
    const zeroed = {
      category_weights: { [GradeCategory.LAB]: 100, [GradeCategory.BONUS]: 0 },
    } as unknown as Course;

    expect(carriesBonus(zeroed)).toBe(false);
  });

  it("is true for an ordinary grade marked above its maximum", () => {
    expect(carriesBonus(plain, [grade(11, 10) as Grade])).toBe(true);
  });

  it("is false for a course with neither", () => {
    expect(carriesBonus(plain, [grade(9, 10) as Grade])).toBe(false);
    expect(carriesBonus(plain, [])).toBe(false);
  });

  it("reads the grades off a course detail when none are passed", () => {
    const detail = {
      category_weights: { [GradeCategory.LAB]: 100 },
      grades: [grade(11, 10)],
    } as unknown as CourseDetail;

    expect(carriesBonus(detail)).toBe(true);
  });
});

/**
 * Bonus is the footnote to a course rather than one of its parts, so it reads
 * last however the enum is declared or the API happened to order the weights.
 */
describe("bonusLast", () => {
  it("moves bonus to the end", () => {
    expect(
      bonusLast([GradeCategory.BONUS, GradeCategory.LAB, GradeCategory.FINAL])
    ).toEqual([GradeCategory.LAB, GradeCategory.FINAL, GradeCategory.BONUS]);
  });

  it("leaves the order of everything else alone", () => {
    const ordinary = [GradeCategory.FINAL, GradeCategory.LAB, GradeCategory.QUIZ];

    expect(bonusLast(ordinary)).toEqual(ordinary);
  });

  it("does not mutate what it was given", () => {
    const given = [GradeCategory.BONUS, GradeCategory.LAB];
    bonusLast(given);

    expect(given).toEqual([GradeCategory.BONUS, GradeCategory.LAB]);
  });
});
