# TAAS test checklist (run on a Windows PC, with a TEST blog)

Tick each line. Write down anything that fails, with the message shown on screen.

## A. Live checks of the code (needs internet)
| # | Step | Pass when | Result |
| --- | --- | --- | --- |
| A1 | `python phase1_check.py` | A draft test post appears in your Blogger test blog | [ ] |
| A2 | `python phase1_check.py --link "kw one=https://your-site.com/a" --link "kw two=https://your-site.com/b"` | Output says OK for both links, and both links work when clicked | [ ] |
| A3 | `python phase1_check.py --switch-account` | The Google account chooser appears and a second account works | [ ] |
| A4 | `python phase23_check.py --url URL1 --url URL2 --keywords "k1, k2, k3, k4, k5"` | Details are detected (or a clear message), article passes all checks, article_preview.html has 2 working links | [ ] |

## B. The app (python -m taas, then the .exe)
| # | Area | What to do | Pass when | Result |
| --- | --- | --- | --- | --- |
| B1 | Sign-in | Sign in, close the app, open it again | No new sign-in needed; posting still works | [ ] |
| B2 | Sign-in | Remove TAAS access in your Google account, then post | A message asks you to sign in again | [ ] |
| B3 | Input | Try 1 address, 4 addresses, a bad address, 4 keywords, 11 keywords | Each is blocked with a clear message | [ ] |
| B4 | Pages | Use a normal page, a page that blocks tools, a page that needs JavaScript, a made-up address | Details appear, or you are asked to type them | [ ] |
| B5 | Details | Correct the brand, category and country | Your corrections are kept when you press Back and forward | [ ] |
| B6 | Article | Write 5 articles from different inputs | Each has 300-400 words, every keyword, exactly one link per address, no brand or domain name | [ ] |
| B7 | Uniqueness | Write twice with the same input | The two articles differ in angle and wording | [ ] |
| B8 | Reading | Read 5 articles for stock AI phrases and repetition | The reviewer accepts them | [ ] |
| B9 | Editing | Edit text, change a link keyword, click Check again | Links and checks update correctly | [ ] |
| B10 | Posting | Post as draft, then live | Both appear in Blogger with correct links | [ ] |
| B11 | Safeguards | Set a limit of 1, post live twice; then post the same addresses again | Second live post is blocked; repeat warning shows | [ ] |
| B12 | Errors | Turn the internet off and post; enter a wrong Gemini key | Clear messages; the article stays on screen | [ ] |
| B13 | Settings | Change the word range to 150-250 and write | Article length follows the new range (or checks list the problem) | [ ] |

## C. The .exe (after build_exe.bat)
| # | Step | Pass when | Result |
| --- | --- | --- | --- |
| C1 | Copy the `release` folder to a Windows PC that has no Python | TAAS.exe opens | [ ] |
| C2 | Run the whole flow once with real inputs | A post is created in the test blog | [ ] |
| C3 | Look for your Gemini key inside the release folder | It is not there | [ ] |
| C4 | Give the app to your team and run real inputs | The team signs off | [ ] |
