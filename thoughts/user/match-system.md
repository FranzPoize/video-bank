# Match system

## What is it
Add a new concept of Match with statistics to link videos to

## Feature list
Match should be on the home page. Videos should have their own page now.
Add Matches. Matches (like basketball matches) have a list of videos linked to them, they have a date and a name. They also have statistics:
* Minutes played (MP)
* Points (PTS)
* 2 points attempts (2PA)
* 2 points made (2PM)
* 3 points attempts (3PA)
* 3 points made (2PM)
* Free throw attemps (FTA)
* Free throw made (FTM)
* Offensive rebounds (ORB)
* Defensive rebounds (ORB)
* Total Rebounds (TRB)
* Assists (AST)
* Steals (STL)
* Blocks (BLK)
* Turnover (TO)
* Personal Fouls (PF)

Calculated Stats:
* 2 points percentage (2P%) = 2PM / 2PA
* 3 points percentage (3P%) = 3PM / 3PA
* Field Goal Attemps (FGA) = 2PA + 3PA
* Field Goal Made (FGM) = 2PM + 3PM
* Free Throw Percentage (FT%) = FTM / FTA
* Effective field goal percentage = (FGM + (0.5 * 3PM)) / FGA
* True shooting percentage = PTS / (2 * FGA + 0.44 * FTA)


IMPORTANT ! If you see anything in the list of features that is unclear please ask questions.
IMPORTANT ! If you think something is a must have that is a must have you should add it

## Tech

* Use any tech, framework or lib that seems relevant

Please provide a list of choice of tech that you could use to the user

## How to deliver

### Make a plan
* Make a plan by asking questions to the user
* making obvious decisions and provide this plan in md form next to this file.
* The plan must be incremental and have checkpoint signaled by a "CHECKPOINT HERE STOP AND REPORT TO PARENT AGENT !" where functionnality should be validated
* The plan should be easy to understand and not go into deep details if there is stuff that are still up in the air please signal it with "You should discuss this with the user when you implement it"

IMPORTANT ! Tell the executor to stop on each checkpoint

### Wait for validation
* The user will validate the plan and then prompt you to start development

### Start the development cycle
1. Develop the app up to the next checkpoint signaled by "CHECKPOINT HERE STROP AND REPORT TO PARENT AGENT!" stop there
2. Let the user test the app and ask you for correction
3. Do those correction and go to step 2.
4. When the user is happy got to step 1.

### The code
* Make the code as simple as possible
* The code should be testable
* Avoid inversion of control as much as possible
* Make unit tests for the app

