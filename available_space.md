# Display available size on server

## What is it
We want to display the available space on the machine to the users and also forbid upload that would fill more than 95% of the local available space

## Feature list
* Add a way to query the current server available space
* Add a UI element to display this size. When there is not a lot of space left make the element red

IMPORTANT ! If you see anything in the list of features that is unclear please ask question.
IMPORTANT ! If you think something is a must have that is a must have you should add it

## Tech

* Use any tech, framework or lib that seems relevant
* The web app must be easy to selfhost on ubuntu

Please provide a list of choice of tech that you could use to the user

## How to deliver

### Make a plan
* Make a plan by asking questions to the user
* making obvious decisions and provide this plan in md form next to this file.
* The plan must be incremental and have checkpoint signaled by a "CHECKPOINT HERE !" where functionnality should be validated
* The plan should be easy to understand and not go into deep details if there is stuff that are still up in the air please signal it with "You should discuss this with the user when you implement it"

IMPORTANT ! Tell the executor to stop on each checkpoint

### Wait for validation
* The user will validate the plan and then prompt you to start development

### Start the development cycle
1. Develop the app up to the next checkpoint signaled by "CHECKPOINT HERE !" stop there
2. Let the user test the app and ask you for correction
3. Do those correction and go to step 2.
4. When the user is happy got to step 1.

### The code
* Make the code as simple as possible
* The code should be testable
* Avoid inversion of control as much as possible
* Make unit tests for the app

