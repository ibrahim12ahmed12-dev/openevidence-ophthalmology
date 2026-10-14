# Pilot guide (no coding needed)

This guide takes you from a fresh computer to a finished 10-case pilot. You
will use **Pilot Desk**, a set of pages that open in your web browser.

**Does it need commands?** No, not for the pilot. You start Pilot Desk by
double-clicking a file, and everything else is buttons and forms. Pilot Desk
runs only on your computer: the address is `127.0.0.1`, which means "this
machine", and nothing is uploaded anywhere. The only things that still need a
command are the final statistical analysis and rebuilding the pilot from
scratch. Those are for whoever runs the statistics.

**Where the data go.** Everything you enter stays in the project's `data`
folder on your computer. Pilot runs go in `data/pilot`, which is kept apart
from the main study. The `data` folder is never uploaded to GitHub, because the
repository is public and it contains answer keys and case text. Back it up to
your institution's approved storage instead.

---

## 1. One-time setup (about 15 minutes)

1. **Install Python 3** from <https://www.python.org/downloads/>.
   On Windows, tick **"Add python.exe to PATH"** on the first installer screen.
2. **Download the project.** On the GitHub page, choose the branch
   `claude/openevidence-ophthalmology-workflow-8o2sls`, then **Code → Download ZIP**.
   Unzip it somewhere you will find again, for example *Documents*.
3. **Add the workbook.** Copy `2026_10_03_OpenEvidence-Data_ModelFamily.xlsx`
   into the unzipped folder's `data/source/` folder.
4. **Start Pilot Desk.**
   * **Mac:** double-click **Start Pilot Desk.command**. The first time, macOS
     may refuse to open it. If so, right-click it, choose **Open**, then **Open**.
   * **Windows:** double-click **Start Pilot Desk.bat**.

   A black window opens and your browser shows Pilot Desk. On the first start
   it reads the workbook and creates the pilot folder, which takes a few
   seconds. **Keep the black window open while you work**; closing it stops
   Pilot Desk. Your work is saved after every button press.

If the browser does not open, go to <http://127.0.0.1:8765/> yourself.

---

## 2. The home page

* **Readiness.** Every item must be green ("ready") before the first pilot
  run. Items marked "before grading" can wait until collection is done.
* **Pilot cases.** The 10 cases (31, 75, 100, 108, 156, 173, 225, 301, 390,
  414). For each case, work left to right: image-arm text → images → record runs.
* **Pilot sign-off** (bottom of the page). Record who checked the OpenEvidence
  model selector, and name the collector(s), the two graders and the adjudicator.
* The top bar has **Run checks**, **Export for grading** and **Answer keys
  (coordinator)**.

The answer-key page shows answers. Never open it where a collector or grader
can see it. The collector pages never show case titles or answers.

---

## 3. Prepare one case (worked example: case 390)

### 3a. Image-arm text: prep team, about 5 minutes per case

Click the status link in the **Image-arm text** column.

* The **left** box is the text-only version. Text that is ~~struck through~~
  is proposed for removal: the written figure legend, which the image replaces.
  **Highlighted** words are things you must check, such as a non-visual detail
  (which eye, timing) that sits inside the legend being removed.
* The **right** box is the proposed image-arm text. Each "attached" is
  highlighted so you can confirm figure references read correctly.
* **Please check** lists the automatic warnings. The most common one is a
  sentence in the story that cites a figure and also describes what it shows.
  Under the provisional rule those sentences stay in.

The rule: remove the legend; keep everything that is not a visual finding
(age, which eye, timing, history); keep story sentences that cite a figure,
written as "(Figure 1 attached)". Do not reword clinical facts.

For case 390, the legend to remove is the last paragraph, beginning
"Clinical photograph at presentation…". The highlighted "left eye" and "at
presentation" are already in the story, so nothing needs to move. One thing to
change by hand: "The left eye is shown in Figure 1." should read "…shown in
Figure 1 (attached)."

Edit the big box if needed, type your initials, choose **Approve for
collection**, and press **Save**.

### 3b. Images: prep team

1. Get the published figure(s) at the highest resolution with the **Figures**
   page (section 3c). It keeps the originals unchanged in `data/images/original/`.
2. Make a copy and crop out panel letters, captions and any text naming a
   diagnosis. Keep arrows.
3. Save the prepared copy in `data/images/prepared/` as **IMG-390-1.png** (then
   IMG-390-2.png, and so on). Only these neutral names: never a diagnosis or title.
4. Click the **Images** link for the case and reload the page. Your file
   appears. Fill in the figure number and the original file name, tick the
   modality, describe what you cropped, tick **I checked this image…**, add
   your initials and **Save**.
5. If a case's figures cannot be uploaded (for example, video only), tick the
   box saying so instead. Its image runs will then be recorded as
   "unavailable", which is never counted as wrong.

When both steps are done, the case's image prompts become ready automatically.

---

## 3c. Download case figures (Figures page)

Click **Figures** in the top bar. Pilot Desk reads each case's article link from
the workbook, finds the figures shown in the **case presentation**, and saves
the largest version offered for each one, including every panel. Figures from
the answer or discussion part of the article, supplementary eFigures,
thumbnails, journal logos and related-article pictures are skipped. Files are
stored **unchanged** in `data/images/original/<case>/`, for example
`data/images/original/390/IMG-390-1.jpg`. Your cropped copies live separately
in `data/images/prepared/`.

**Step 1: test three cases.** The box is pre-filled with three pilot cases.
Press **Download test cases**. It takes a minute or two, because Pilot Desk
waits 6–8 seconds between requests on purpose.

**Step 2: check the test.** Open each case's **Review** page and the
**inspection report**. The report lists every image found on each article page
and which one was chosen. Check that:

* every figure the case text mentions is there;
* all panels are there;
* the images are full size, not small previews;
* nothing came from the answer or discussion section.

If all is right, sign off with your initials. The expand buttons only work
after this sign-off.

**Step 3: expand.** Use **Download all 10 pilot cases**, and later **Download
all included cases**. All 421 included cases take about 2–3 hours. You can
press **Stop** at any time. Pressing a download button again resumes: finished
cases and files are skipped and never duplicated.

**Review each figure (prep team).** On a case's Review page:

1. Click the image to open it full size. Look for burned-in text, arrows with
   labels, panel captions or stain names that could give the answer away.
2. Choose whether the figure belongs to **this case's presentation**. The
   published caption and the case text (the "Case text" box) are shown to help
   you match them. Tick the box if the image itself contains revealing text.
3. Only after **Confirmed** can you press **Make prepared copy for cropping**.
   This puts an identical copy in `data/images/prepared/`. Crop that copy in any
   image editor (Preview, Paint, Photos) and keep arrows. Then describe it on
   the case's **Images** page as before.

Nothing is approved automatically. The original is never changed.

### When a figure cannot be downloaded automatically

Pilot Desk does not try to get around access controls. It never signs in,
never uses your browser's saved login, never solves "are you a robot" checks,
and never retries a refusal. When it meets any of these, it stops for that case
and lists it under **Needs manual download**:

* a sign-in or purchase page;
* the site's robots.txt rules forbidding automated access;
* a bot check;
* a refused image;
* a missing link in the workbook. Case 183's link field contains a title
  instead of a web address.

If the site shows a bot check or asks it to slow down, the whole batch pauses.

To download a listed figure yourself in a normal browser:

1. On the case's Review page, click **Open the article in your browser**. If
   your university gives you JAMA access, sign in the usual way: through the
   library's journal link, or "Sign in → Access through your institution" on
   the article page.
2. Scroll to the case description. Ignore anything under "Diagnosis" or
   "Discussion".
3. On the figure, click **View Large** (or the figure itself) to open the
   full-size image. If there is a **Download** option that gives an image (not a
   PowerPoint slide), use it. Otherwise right-click the large image → **Save
   image as…**.
4. Back on the Review page, under **Add a figure downloaded in your browser**,
   choose the file and type the figure number. If a figure comes as several
   files, use part letters a, b, c… You can also right-click the image → **Copy
   image address** and paste it in the image-address box, and add your initials.
   The file is saved unchanged under a neutral name and still needs review.

If an article has no figures you can reach, or a figure is video only, record
that on the case's **Images** page ("cannot be uploaded"). Its image runs will
be marked unavailable, which is never counted as wrong.

**Network note.** Downloads use the computer's own internet connection. On a
university network, articles your library subscribes to may be reachable. At
home they may not be. Either way, nothing is circumvented.

---

## 4. Record the six OpenEvidence runs for a case (collector)

Click **Record runs**. Six cards appear in the **randomized order**. Work top to
bottom. For each card:

1. In OpenEvidence, open a **new chat**. Never reuse one, even for the same case.
2. Select the model shown on the card (Osler, Sackett or Snow) and check it is selected.
3. Press **Copy prompt** and paste it into OpenEvidence unchanged.
   *Text + image* cards also list the files to attach: attach exactly those,
   in the same message.
4. Press **Start** on the card as you submit in OpenEvidence, and **Stop** when
   the answer has finished. The seconds fill in for you.
5. Copy the whole answer, including the reference list, and paste it into
   the big box.
6. Count the citations. Look at each one: if any is the source JAMA Clinical
   Challenge, its answer, or a case report of the same patient, choose **Yes**
   and name it in the note box. Otherwise choose **No**. Use **Unclear** only
   if you really cannot tell.
7. Optionally upload a screenshot. Type your initials, tick the two
   confirmation boxes, and press **Save this run**.

The date, time and time zone fill in automatically. If something is missing,
the page says so and nothing is saved.

**If something goes wrong** (an error, the wrong model selected, a reused chat,
an upload failure), choose **Failed** as the result, say what happened, and
save. Then repeat that run in a new chat on the same card. Both attempts are
kept, and the first completed one is used.

**Never repeat a run because the answer looks wrong.** Once a run is saved as
completed, the card locks.

You may start other runs while Snow is thinking (it can take several minutes),
as long as each is in its own chat.

---

## 5. Export for grading (coordinator)

1. Click **Export for grading → Create grading packets now**.
2. Open `data/pilot/grading/packets/`. Send grader 1 **only** the file starting
   `grader_G1_`, grader 2 **only** `grader_G2_`, and both the `responses`
   folder and `docs/SOP_grading.md`. The `interp_` files are the
   image-interpretation packets; they go out the same way, and the graders
   also need the prepared image files.
3. **Never send** anything from `data/pilot/grading/private`. It links each
   response to its model.
4. Graders open their file in Excel, fill in the empty columns, save under the
   same name (CSV format) and send it back.
5. Put returned files in `data/pilot/grading/returns/`, then click **Combine
   returned grades**. Any disagreements go into
   `data/pilot/grading/adjudication/adjudication_packet.csv` for the adjudicator.
   The adjudicator saves a filled copy as `adjudication_return.csv` in the same
   folder; then press **Combine returned grades** again.

Graders need the accepted diagnosis synonyms for the 10 pilot cases before they
start. The coordinator enters them on the **Answer keys (coordinator)** page,
under "Accepted diagnosis synonyms". They appear in packets exported after that,
so enter them **before** pressing *Create grading packets*.

---

## 6. Run checks

Click **Run checks** at any time. Red **errors** must be fixed (the message
names the run, such as `P-390-C4`). Amber **warnings** need someone to decide.
Grey notes are for information. A saved copy of each report is kept in
`data/pilot/reports/`.

---

## 7. After the pilot

Pilot answers stay in `data/pilot`. They are never combined with the main study
unless the team records that decision (decision log D19). Once the protocol is
final, the main collection uses the same Pilot Desk workflow on the full
schedule. Ask the person running the statistics to calculate the pilot
discordance for the power estimate (`Rscript R/power.R data/pilot docs/power`).

## Troubleshooting

| Problem | What to do |
|---|---|
| "Python 3 is not installed" | Install it (step 1), then double-click again |
| Browser shows "can't connect" | The black window was closed; double-click the launcher again |
| "Put the study workbook (.xlsx) in data/source" | Copy the workbook there (step 3) |
| A card says NOT READY | The case's image-arm text is not approved or its images are not described (section 3) |
| I saved a run with a mistake | Do not edit files by hand; tell the coordinator, who records a note |
| Port already in use | Pilot Desk is already running in another window; use that one |
