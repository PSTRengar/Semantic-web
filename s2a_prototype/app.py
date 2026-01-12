from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import Flask, request, render_template_string
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD


APP_TITLE = "S2A - Smart Academic Advisor (CSV→KG + Constraints + Explain + Query Templates)"
BASE = "http://example.org/s2a#"
S2A = Namespace(BASE)
DATA_DIR = Path("data")


# -------------------------
# SPARQL templates (Step 4)
# -------------------------
def sparql_templates(student_iri: str) -> Dict[str, str]:
    """
    Returns {template_name: sparql_query}.
    student_iri is injected into templates needing a student.
    """
    # We place the IRI directly as <...> in SPARQL.
    s = f"<{student_iri}>" if student_iri else "?s"

    return {
        "1) Courses + prerequisites + metadata": f"""PREFIX : <{BASE}>
SELECT ?courseLabel ?credits ?semester ?difficulty ?track ?prereqLabel WHERE {{
  ?c a :Course ; :label ?courseLabel .
  OPTIONAL {{ ?c :credits ?credits . }}
  OPTIONAL {{ ?c :semester ?semester . }}
  OPTIONAL {{ ?c :difficulty ?difficulty . }}
  OPTIONAL {{ ?c :track ?track . }}
  OPTIONAL {{
    ?c :hasPrerequisite ?p .
    ?p :label ?prereqLabel .
  }}
}}
ORDER BY ?courseLabel
""",
        "2) Skills taught by each course": f"""PREFIX : <{BASE}>
SELECT ?courseLabel ?skillLabel WHERE {{
  ?c a :Course ; :label ?courseLabel ; :teachesSkill ?sk .
  ?sk :label ?skillLabel .
}}
ORDER BY ?courseLabel ?skillLabel
""",
        "3) Student profile (taken + interests + constraints)": f"""PREFIX : <{BASE}>
SELECT ?studentLabel ?target ?maxC ?maxD ?track ?takenCourseLabel ?interestSkillLabel WHERE {{
  {s} a :Student ; :label ?studentLabel .
  OPTIONAL {{ {s} :targetSemester ?target . }}
  OPTIONAL {{ {s} :maxCredits ?maxC . }}
  OPTIONAL {{ {s} :maxDifficulty ?maxD . }}
  OPTIONAL {{ {s} :preferredTrack ?track . }}
  OPTIONAL {{
    {s} :takesCourse ?c .
    ?c :label ?takenCourseLabel .
  }}
  OPTIONAL {{
    {s} :hasInterest ?sk .
    ?sk :label ?interestSkillLabel .
  }}
}}
ORDER BY ?studentLabel ?takenCourseLabel ?interestSkillLabel
""",
        "4) Eligible courses for student (prereqs satisfied, not yet taken)": f"""PREFIX : <{BASE}>
SELECT DISTINCT ?courseLabel WHERE {{
  {s} a :Student .
  ?course a :Course ; :label ?courseLabel .

  # not taken
  FILTER NOT EXISTS {{ {s} :takesCourse ?course . }}

  # prereq constraint: no prerequisite OR all prerequisites taken
  FILTER NOT EXISTS {{
    ?course :hasPrerequisite ?p .
    FILTER NOT EXISTS {{ {s} :takesCourse ?p . }}
  }}
}}
ORDER BY ?courseLabel
""",
        "5) Interest-matched courses for student (ignoring credit/track/difficulty)": f"""PREFIX : <{BASE}>
SELECT DISTINCT ?courseLabel ?skillLabel WHERE {{
  {s} a :Student ; :hasInterest ?sk .
  ?course a :Course ; :label ?courseLabel ; :teachesSkill ?sk .
  ?sk :label ?skillLabel .

  # not taken
  FILTER NOT EXISTS {{ {s} :takesCourse ?course . }}

  # prereq satisfied
  FILTER NOT EXISTS {{
    ?course :hasPrerequisite ?p .
    FILTER NOT EXISTS {{ {s} :takesCourse ?p . }}
  }}
}}
ORDER BY ?courseLabel ?skillLabel
""",
        "6) Careers matched by student interests (and why)": f"""PREFIX : <{BASE}>
SELECT DISTINCT ?careerLabel ?skillLabel WHERE {{
  {s} a :Student ; :hasInterest ?sk .
  ?career a :Career ; :label ?careerLabel ; :requiresSkill ?sk .
  ?sk :label ?skillLabel .
}}
ORDER BY ?careerLabel ?skillLabel
""",
        "7) Papers related to student interests": f"""PREFIX : <{BASE}>
SELECT DISTINCT ?paperLabel ?skillLabel WHERE {{
  {s} a :Student ; :hasInterest ?sk .
  ?paper a :ResearchPaper ; :label ?paperLabel ; :relatedTo ?sk .
  ?sk :label ?skillLabel .
}}
ORDER BY ?paperLabel ?skillLabel
""",
        "8) Courses → Skills → Careers (show course-career connection)": f"""PREFIX : <{BASE}>
SELECT DISTINCT ?courseLabel ?skillLabel ?careerLabel WHERE {{
  ?course a :Course ; :label ?courseLabel ; :teachesSkill ?sk .
  ?sk :label ?skillLabel .
  ?career a :Career ; :label ?careerLabel ; :requiresSkill ?sk .
}}
ORDER BY ?courseLabel ?careerLabel ?skillLabel
""",
    }


# -------------------------
# UI (adds template dropdown)
# -------------------------
HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{title}}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial; margin: 24px; line-height: 1.4; }
    .row { display: flex; gap: 16px; flex-wrap: wrap; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; min-width: 360px; flex: 1; }
    select, textarea, button { width: 100%; padding: 10px; margin-top: 8px; }
    textarea { height: 190px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }
    button { cursor: pointer; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas; }
    ul { margin: 8px 0 0 18px; }
    .muted { color: #666; }
    .pill { display: inline-block; padding: 2px 8px; border: 1px solid #ccc; border-radius: 999px; margin-right: 6px; }
    details { margin-top: 6px; }
    summary { cursor: pointer; }
    .kv { margin: 6px 0; }
  </style>
</head>
<body>
  <h1>{{title}}</h1>
  <p class="muted">
    Prototype: CSV→KG integration + SPARQL + personalized recommendations with constraints + explainable paths + query templates.
  </p>

  <div class="row">
    <div class="card">
      <h3>1) Choose a student profile</h3>
      <form method="get" action="/">
        <label>Student</label>
        <select name="student">
          {% for s in students %}
            <option value="{{s['iri']}}" {% if s['iri']==selected_student %}selected{% endif %}>{{s['label']}}</option>
          {% endfor %}
        </select>
        <button type="submit">Load Profile</button>
      </form>

      {% if profile %}
        <hr>
        <h4>Profile</h4>

        <div><span class="pill">Courses taken</span></div>
        <ul>
          {% for c in profile['taken'] %}
            <li>{{c}}</li>
          {% endfor %}
        </ul>

        <div style="margin-top:10px;"><span class="pill">Interests</span></div>
        <ul>
          {% for i in profile['interests'] %}
            <li>{{i}}</li>
          {% endfor %}
        </ul>

        <div style="margin-top:10px;"><span class="pill">Constraints</span></div>
        <ul>
          <li>target_semester: {{profile['constraints']['target_semester']}}</li>
          <li>max_credits: {{profile['constraints']['max_credits']}}</li>
          <li>max_difficulty: {{profile['constraints']['max_difficulty']}}</li>
          <li>preferred_track: {{profile['constraints']['preferred_track']}}</li>
        </ul>
      {% endif %}
    </div>

    <div class="card">
      <h3>2) Personalized recommendations</h3>
      {% if rec %}
        <h4>Recommended courses (eligible + aligned)</h4>
        {% if rec['courses'] %}
          <ul>
            {% for item in rec['courses'] %}
              <li>
                <b>{{item['course']}}</b>
                <span class="muted">— matches interests:</span> {{", ".join(item['matched_interests'])}}
                <details>
                  <summary>Why recommended (explain chain)</summary>

                  <div class="kv"><b>Interest match path</b>:</div>
                  <ul>
                    {% for p in item['explain']['interest_paths'] %}
                      <li class="mono">{{p}}</li>
                    {% endfor %}
                  </ul>

                  <div class="kv"><b>Prerequisite check</b>:</div>
                  {% if item['explain']['prereq_paths'] %}
                    <ul>
                      {% for p in item['explain']['prereq_paths'] %}
                        <li class="mono">{{p}}</li>
                      {% endfor %}
                    </ul>
                  {% else %}
                    <div class="muted">No prerequisites.</div>
                  {% endif %}

                  <div class="kv"><b>Constraint checks</b>:</div>
                  <ul>
                    {% for line in item['explain']['constraint_checks'] %}
                      <li class="mono">{{line}}</li>
                    {% endfor %}
                  </ul>

                  <div class="kv"><b>Selection (credit budget)</b>:</div>
                  <div class="mono">{{item['explain']['budget_line']}}</div>
                </details>
              </li>
            {% endfor %}
          </ul>
        {% else %}
          <p class="muted">No eligible course found with current profile + constraints.</p>
        {% endif %}

        <h4 style="margin-top:14px;">Suggested careers (skill match)</h4>
        {% if rec['careers'] %}
          <ul>
            {% for item in rec['careers'] %}
              <li>
                <b>{{item['career']}}</b> <span class="muted">— matched skills:</span> {{", ".join(item['matched_skills'])}}
                <details>
                  <summary>Why suggested</summary>
                  <div class="kv"><b>Match paths</b>:</div>
                  <ul>
                    {% for p in item['explain_paths'] %}
                      <li class="mono">{{p}}</li>
                    {% endfor %}
                  </ul>
                </details>
              </li>
            {% endfor %}
          </ul>
        {% else %}
          <p class="muted">No career match found.</p>
        {% endif %}

        <h4 style="margin-top:14px;">Relevant papers (by interest skills)</h4>
        {% if rec['papers'] %}
          <ul>
            {% for item in rec['papers'] %}
              <li>
                {{item['paper']}}
                <details>
                  <summary>Why relevant</summary>
                  <ul>
                    {% for p in item['explain_paths'] %}
                      <li class="mono">{{p}}</li>
                    {% endfor %}
                  </ul>
                </details>
              </li>
            {% endfor %}
          </ul>
        {% else %}
          <p class="muted">No paper match found.</p>
        {% endif %}
      {% else %}
        <p class="muted">Select a student profile to see recommendations.</p>
      {% endif %}
    </div>
  </div>

  <div class="row" style="margin-top:16px;">
    <div class="card">
      <h3>3) Run a SPARQL query</h3>

      <label>Query template</label>
      <select id="tpl">
        {% for name in template_names %}
          <option value="{{name}}" {% if name==selected_template %}selected{% endif %}>{{name}}</option>
        {% endfor %}
      </select>

      <form method="post" action="/query" id="qform">
        <input type="hidden" name="student" value="{{selected_student}}">
        <input type="hidden" name="template_name" id="template_name" value="{{selected_template}}">
        <label>SPARQL</label>
        <textarea name="sparql" id="sparql">{{sparql}}</textarea>
        <button type="submit">Run Query</button>
      </form>

      <p class="muted">Prefix: <span class="mono">PREFIX : &lt;http://example.org/s2a#&gt;</span></p>

      <script>
        // templates are injected from server
        const templates = {{ templates_json | safe }};
        const tplSel = document.getElementById("tpl");
        const sparqlBox = document.getElementById("sparql");
        const templateNameHidden = document.getElementById("template_name");

        tplSel.addEventListener("change", () => {
          const name = tplSel.value;
          templateNameHidden.value = name;
          sparqlBox.value = templates[name] || sparqlBox.value;
        });
      </script>
    </div>

    <div class="card">
      <h3>Query results</h3>
      {% if qerror %}
        <p style="color:#b00020;"><b>Error:</b> {{qerror}}</p>
      {% endif %}
      {% if qrows is not none %}
        <p class="muted">Returned {{qrows|length}} row(s).</p>
        <div class="mono" style="white-space: pre-wrap;">
{% for row in qrows %}
{{row}}
{% endfor %}
        </div>
      {% else %}
        <p class="muted">No query executed yet.</p>
      {% endif %}
    </div>
  </div>
</body>
</html>
"""


# -------------------------
# CSV -> KG
# -------------------------
def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing CSV: {path.as_posix()}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _as_uri(local_id: str) -> URIRef:
    safe = local_id.strip().replace(" ", "_")
    return S2A[safe]


def build_graph_from_csv(data_dir: Path) -> Graph:
    g = Graph()
    g.bind("", S2A)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)

    # ---- TBox ----
    for cls in ["Student", "Course", "Skill", "Career", "ResearchPaper"]:
        g.add((_as_uri(cls), RDF.type, OWL.Class))

    def objprop(p: str, domain: str, range_: str, transitive: bool = False):
        p_uri = _as_uri(p)
        g.add((p_uri, RDF.type, OWL.ObjectProperty))
        g.add((p_uri, RDFS.domain, _as_uri(domain)))
        g.add((p_uri, RDFS.range, _as_uri(range_)))
        if transitive:
            g.add((p_uri, RDF.type, OWL.TransitiveProperty))

    objprop("hasPrerequisite", "Course", "Course", transitive=True)
    objprop("takesCourse", "Student", "Course")
    objprop("hasInterest", "Student", "Skill")
    objprop("teachesSkill", "Course", "Skill")
    objprop("requiresSkill", "Career", "Skill")
    objprop("relatedTo", "ResearchPaper", "Skill")

    def datprop(p: str, domain: str, range_: URIRef):
        p_uri = _as_uri(p)
        g.add((p_uri, RDF.type, OWL.DatatypeProperty))
        g.add((p_uri, RDFS.domain, _as_uri(domain)))
        g.add((p_uri, RDFS.range, range_))

    # label
    g.add((_as_uri("label"), RDF.type, OWL.DatatypeProperty))
    g.add((_as_uri("label"), RDFS.range, XSD.string))

    # course metadata
    datprop("credits", "Course", XSD.integer)
    datprop("semester", "Course", XSD.integer)
    datprop("difficulty", "Course", XSD.integer)
    datprop("track", "Course", XSD.string)

    # student constraints (optional)
    datprop("targetSemester", "Student", XSD.integer)
    datprop("maxCredits", "Student", XSD.integer)
    datprop("maxDifficulty", "Student", XSD.integer)
    datprop("preferredTrack", "Student", XSD.string)

    # helpers
    def add_label(node: URIRef, label: str):
        g.add((node, _as_uri("label"), Literal(label, datatype=XSD.string)))

    def add_int(node: URIRef, prop: str, val: str):
        if val is None or str(val).strip() == "":
            return
        g.add((node, _as_uri(prop), Literal(int(val), datatype=XSD.integer)))

    def add_str(node: URIRef, prop: str, val: str):
        if val is None or str(val).strip() == "":
            return
        g.add((node, _as_uri(prop), Literal(str(val), datatype=XSD.string)))

    # ---- Load CSVs ----
    for row in _read_csv(data_dir / "courses.csv"):
        c = _as_uri(row["course_id"])
        g.add((c, RDF.type, _as_uri("Course")))
        add_label(c, row.get("label", row["course_id"]))
        add_int(c, "credits", row.get("credits"))
        add_int(c, "semester", row.get("semester"))
        add_int(c, "difficulty", row.get("difficulty"))
        add_str(c, "track", row.get("track"))

    for row in _read_csv(data_dir / "prerequisites.csv"):
        g.add((_as_uri(row["course_id"]), _as_uri("hasPrerequisite"), _as_uri(row["prereq_id"])))

    for row in _read_csv(data_dir / "course_skills.csv"):
        sk = _as_uri(row["skill_id"])
        g.add((sk, RDF.type, _as_uri("Skill")))
        add_label(sk, row.get("skill_label", row["skill_id"]))
        g.add((_as_uri(row["course_id"]), _as_uri("teachesSkill"), sk))

    for row in _read_csv(data_dir / "careers.csv"):
        car = _as_uri(row["career_id"])
        g.add((car, RDF.type, _as_uri("Career")))
        add_label(car, row.get("label", row["career_id"]))

    for row in _read_csv(data_dir / "career_skills.csv"):
        car = _as_uri(row["career_id"])
        sk = _as_uri(row["skill_id"])
        g.add((sk, RDF.type, _as_uri("Skill")))
        g.add((car, _as_uri("requiresSkill"), sk))

    for row in _read_csv(data_dir / "papers.csv"):
        p = _as_uri(row["paper_id"])
        g.add((p, RDF.type, _as_uri("ResearchPaper")))
        add_label(p, row.get("label", row["paper_id"]))

    for row in _read_csv(data_dir / "paper_skills.csv"):
        p = _as_uri(row["paper_id"])
        sk = _as_uri(row["skill_id"])
        g.add((sk, RDF.type, _as_uri("Skill")))
        g.add((p, _as_uri("relatedTo"), sk))

    # Students (supports both old and new students.csv)
    for row in _read_csv(data_dir / "students.csv"):
        st = _as_uri(row["student_id"])
        g.add((st, RDF.type, _as_uri("Student")))
        add_label(st, row.get("label", row["student_id"]))

        taken_cell = (row.get("taken_courses") or "").strip()
        taken = [x.strip() for x in taken_cell.split(";") if x.strip()]
        if len(taken) == 1 and "," in taken[0]:
            taken = [x.strip() for x in taken[0].split(",") if x.strip()]
        for c_id in taken:
            g.add((st, _as_uri("takesCourse"), _as_uri(c_id)))

        interests = [x.strip() for x in (row.get("interests") or "").split(";") if x.strip()]
        for sk_id in interests:
            sk = _as_uri(sk_id)
            g.add((sk, RDF.type, _as_uri("Skill")))
            g.add((st, _as_uri("hasInterest"), sk))

        # constraints (optional columns)
        add_int(st, "targetSemester", row.get("target_semester"))
        add_int(st, "maxCredits", row.get("max_credits"))
        add_int(st, "maxDifficulty", row.get("max_difficulty"))
        add_str(st, "preferredTrack", row.get("preferred_track"))

    return g


# -------------------------
# KG helpers + recommend (with explain)
# -------------------------
def iri_to_label(g: Graph, node: URIRef) -> str:
    lab = g.value(node, _as_uri("label"))
    if lab:
        return str(lab)
    return str(node).split("#")[-1]


def list_students(g: Graph):
    out = []
    for s in g.subjects(RDF.type, _as_uri("Student")):
        out.append({"iri": str(s), "label": iri_to_label(g, s)})
    out.sort(key=lambda x: x["label"])
    return out


def _get_int(g: Graph, subj: URIRef, prop: str) -> Optional[int]:
    v = g.value(subj, _as_uri(prop))
    return int(v) if v is not None else None


def _get_str(g: Graph, subj: URIRef, prop: str) -> Optional[str]:
    v = g.value(subj, _as_uri(prop))
    return str(v) if v is not None else None


def get_profile(g: Graph, student_iri: str):
    s = URIRef(student_iri)
    taken = [iri_to_label(g, c) for c in g.objects(s, _as_uri("takesCourse"))]
    interests = [iri_to_label(g, sk) for sk in g.objects(s, _as_uri("hasInterest"))]
    constraints = {
        "target_semester": _get_int(g, s, "targetSemester"),
        "max_credits": _get_int(g, s, "maxCredits"),
        "max_difficulty": _get_int(g, s, "maxDifficulty"),
        "preferred_track": _get_str(g, s, "preferredTrack"),
    }
    return {"taken": sorted(taken), "interests": sorted(interests), "constraints": constraints}


def _course_meta(g: Graph, course: URIRef) -> Dict[str, Optional[object]]:
    return {
        "credits": _get_int(g, course, "credits") or 0,
        "semester": _get_int(g, course, "semester"),
        "difficulty": _get_int(g, course, "difficulty"),
        "track": _get_str(g, course, "track"),
    }


def _constraint_checks(
    *,
    target_semester: Optional[int],
    max_difficulty: Optional[int],
    preferred_track: Optional[str],
    max_credits: Optional[int],
    current_total_credits: int,
    course_meta: Dict[str, Optional[object]],
) -> Tuple[bool, List[str], str]:
    lines = []
    ok = True

    c_sem = course_meta["semester"]
    c_diff = course_meta["difficulty"]
    c_track = course_meta["track"]
    c_cred = int(course_meta["credits"] or 0)

    if target_semester is None or c_sem is None:
        lines.append(f"semester: course={c_sem} vs target={target_semester} => OK (no/unknown constraint)")
    else:
        if c_sem <= target_semester:
            lines.append(f"semester: course={c_sem} ≤ target={target_semester} => OK")
        else:
            lines.append(f"semester: course={c_sem} > target={target_semester} => FAIL")
            ok = False

    if max_difficulty is None or c_diff is None:
        lines.append(f"difficulty: course={c_diff} vs max={max_difficulty} => OK (no/unknown constraint)")
    else:
        if c_diff <= max_difficulty:
            lines.append(f"difficulty: course={c_diff} ≤ max={max_difficulty} => OK")
        else:
            lines.append(f"difficulty: course={c_diff} > max={max_difficulty} => FAIL")
            ok = False

    if not preferred_track or not c_track:
        lines.append(f"track: course={c_track} vs preferred={preferred_track} => OK (no/unknown constraint)")
    else:
        if c_track == preferred_track:
            lines.append(f"track: course={c_track} == preferred={preferred_track} => OK")
        else:
            lines.append(f"track: course={c_track} != preferred={preferred_track} => FAIL")
            ok = False

    if max_credits is None:
        budget_line = f"credits: course={c_cred}, current_total={current_total_credits}, max=None => selected by relevance"
    else:
        budget_line = f"credits: course={c_cred}, current_total={current_total_credits}, max={max_credits} => decision during selection"

    return ok, lines, budget_line


def recommend(g: Graph, student_iri: str):
    s = URIRef(student_iri)

    taken_courses = set(g.objects(s, _as_uri("takesCourse")))
    interest_skills = set(g.objects(s, _as_uri("hasInterest")))

    # constraints
    target_semester = _get_int(g, s, "targetSemester")
    max_credits = _get_int(g, s, "maxCredits")
    max_difficulty = _get_int(g, s, "maxDifficulty")
    preferred_track = _get_str(g, s, "preferredTrack")

    # gained skills from taken courses
    gained_skills = set()
    for c in taken_courses:
        for sk in g.objects(c, _as_uri("teachesSkill")):
            gained_skills.add(sk)

    # ---- candidate courses ----
    candidates = []
    for course in g.subjects(RDF.type, _as_uri("Course")):
        if course in taken_courses:
            continue

        taught = set(g.objects(course, _as_uri("teachesSkill")))
        matched = taught.intersection(interest_skills)
        if not matched:
            continue

        prereqs = set(g.objects(course, _as_uri("hasPrerequisite")))
        if not prereqs.issubset(taken_courses):
            continue

        meta = _course_meta(g, course)
        ok_non_budget, constraint_lines, budget_line = _constraint_checks(
            target_semester=target_semester,
            max_difficulty=max_difficulty,
            preferred_track=preferred_track,
            max_credits=max_credits,
            current_total_credits=0,
            course_meta=meta,
        )
        if not ok_non_budget:
            continue

        student_label = iri_to_label(g, s)
        course_label = iri_to_label(g, course)

        interest_paths = []
        for sk in matched:
            skill_label = iri_to_label(g, sk)
            interest_paths.append(
                f"{student_label} → hasInterest → {skill_label} ← teachesSkill ← {course_label}"
            )

        prereq_paths = []
        for p in sorted(prereqs, key=lambda x: iri_to_label(g, x)):
            pre_label = iri_to_label(g, p)
            prereq_paths.append(
                f"{course_label} → hasPrerequisite → {pre_label} AND {student_label} → takesCourse → {pre_label}"
            )

        score = (len(matched), -(meta["difficulty"] or 999), -(meta["semester"] or 999))

        candidates.append({
            "course_uri": course,
            "course_label": course_label,
            "matched_interests": sorted(iri_to_label(g, sk) for sk in matched),
            "meta": meta,
            "score": score,
            "explain": {
                "interest_paths": interest_paths,
                "prereq_paths": prereq_paths,
                "constraint_checks": constraint_lines,
                "budget_line": budget_line,
            }
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    # ---- credit budget selection ----
    rec_courses = []
    total = 0
    for item in candidates:
        c_cred = int(item["meta"]["credits"] or 0)
        if max_credits is None:
            item["explain"]["budget_line"] = f"credits: course={c_cred}, current_total={total}, max=None => SELECTED"
            selected = True
        else:
            if total + c_cred <= max_credits:
                item["explain"]["budget_line"] = f"credits: course={c_cred}, current_total={total} + {c_cred} ≤ max={max_credits} => SELECTED"
                selected = True
            else:
                item["explain"]["budget_line"] = f"credits: course={c_cred}, current_total={total} + {c_cred} > max={max_credits} => SKIPPED"
                selected = False

        if not selected:
            continue

        total += c_cred
        rec_courses.append({
            "course": item["course_label"],
            "matched_interests": item["matched_interests"],
            "explain": item["explain"],
        })

    # ---- careers ----
    available_skills = interest_skills.union(gained_skills)
    student_label = iri_to_label(g, s)

    rec_careers = []
    for car in g.subjects(RDF.type, _as_uri("Career")):
        req = set(g.objects(car, _as_uri("requiresSkill")))
        matched = req.intersection(available_skills)
        if not matched:
            continue

        car_label = iri_to_label(g, car)
        paths = []
        for sk in sorted(matched, key=lambda x: iri_to_label(g, x)):
            sk_label = iri_to_label(g, sk)
            if sk in interest_skills:
                paths.append(f"{student_label} → hasInterest → {sk_label} ← requiresSkill ← {car_label}")
            else:
                taught_by = None
                for c in taken_courses:
                    if (c, _as_uri("teachesSkill"), sk) in g:
                        taught_by = iri_to_label(g, c)
                        break
                if taught_by:
                    paths.append(f"{student_label} → takesCourse → {taught_by} → teachesSkill → {sk_label} ← requiresSkill ← {car_label}")
                else:
                    paths.append(f"{sk_label} ← requiresSkill ← {car_label} (skill available)")

        rec_careers.append({
            "career": car_label,
            "matched_skills": sorted(iri_to_label(g, sk) for sk in matched),
            "explain_paths": paths,
        })
    rec_careers.sort(key=lambda x: (-len(x["matched_skills"]), x["career"]))

    # ---- papers ----
    rec_papers = []
    for p in g.subjects(RDF.type, _as_uri("ResearchPaper")):
        related = set(g.objects(p, _as_uri("relatedTo")))
        matched = related.intersection(interest_skills)
        if not matched:
            continue

        paper_label = iri_to_label(g, p)
        paths = []
        for sk in sorted(matched, key=lambda x: iri_to_label(g, x)):
            sk_label = iri_to_label(g, sk)
            paths.append(f"{student_label} → hasInterest → {sk_label} ← relatedTo ← {paper_label}")

        rec_papers.append({"paper": paper_label, "explain_paths": paths})
    rec_papers.sort(key=lambda x: x["paper"])

    return {"courses": rec_courses, "careers": rec_careers, "papers": rec_papers}


# -------------------------
# Flask routes
# -------------------------
app = Flask(__name__)
GRAPH = build_graph_from_csv(DATA_DIR)


@app.get("/")
def home():
    g = GRAPH
    students = list_students(g)

    selected_student = request.args.get("student")
    if not selected_student and students:
        selected_student = students[0]["iri"]

    profile = None
    rec = None
    if selected_student:
        profile = get_profile(g, selected_student)
        rec = recommend(g, selected_student)

    # templates for current student
    templates = sparql_templates(selected_student or "")
    template_names = list(templates.keys())
    selected_template = template_names[0] if template_names else ""
    default_sparql = templates[selected_template] if selected_template else f"PREFIX : <{BASE}>\nSELECT * WHERE {{ ?s ?p ?o }} LIMIT 10"

    # to embed into JS safely, we use a minimal JSON via repr + replacements
    # (safe enough for simple demo strings)
    templates_json = "{\n" + ",\n".join(
        [f"{_js_str(k)}: {_js_str(v)}" for k, v in templates.items()]
    ) + "\n}"

    return render_template_string(
        HTML,
        title=APP_TITLE,
        students=students,
        selected_student=selected_student,
        profile=profile,
        rec=rec,
        template_names=template_names,
        selected_template=selected_template,
        templates_json=templates_json,
        sparql=default_sparql,
        qrows=None,
        qerror=None,
    )


@app.post("/query")
def run_query():
    g = GRAPH
    students = list_students(g)
    selected_student = request.form.get("student") or (students[0]["iri"] if students else None)

    profile = get_profile(g, selected_student) if selected_student else None
    rec = recommend(g, selected_student) if selected_student else None

    templates = sparql_templates(selected_student or "")
    template_names = list(templates.keys())

    selected_template = request.form.get("template_name") or (template_names[0] if template_names else "")
    sparql = request.form.get("sparql") or templates.get(selected_template, "")

    templates_json = "{\n" + ",\n".join(
        [f"{_js_str(k)}: {_js_str(v)}" for k, v in templates.items()]
    ) + "\n}"

    qrows = []
    qerror = None
    try:
        res = g.query(sparql)
        for r in res:
            qrows.append(" | ".join("" if v is None else str(v) for v in r))
    except Exception as e:
        qerror = str(e)

    return render_template_string(
        HTML,
        title=APP_TITLE,
        students=students,
        selected_student=selected_student,
        profile=profile,
        rec=rec,
        template_names=template_names,
        selected_template=selected_template,
        templates_json=templates_json,
        sparql=sparql,
        qrows=qrows,
        qerror=qerror,
    )


def _js_str(s: str) -> str:
    """
    Encode a Python string as a JS string literal (double-quoted).
    Minimal escaping for newlines, backslashes, and quotes.
    """
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return f"\"{s}\""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)