# User and account system

## What is it
We want to add user and accounts.

## Feature list
Accounts are what owns everything, the matches and the videos and the tags.
Users are users and they have a set of rights on the accounts (like CRUD on videos, CRUD on matches, CRUD on tags and settings user rights on the account)
Users have an email and a password. We want to check the email address on signup.
Users can sign up in two ways. Sign up from the sign up form and be invited to an account.
When a users sign up from the sign up form an account is created for this user and that user is the admin of this account.
The admin of the account can invite users to this account and set their rights.

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
