# Clip creator

## What is it

We want to add a new feature that let's us upload a video and chop it into several clip

## Feature List

* New Upload interface that allows to upload big file
    * Right now upload use a simple upload form we want the upload to be asynchronous, when we upload launch a background task in the browser that upload the file
    * List the current uploads in a popup in the bottom left of the web app

* Add a clip feature
    * When on a video add a clip button
    * The clip interface should be the video with a seeker bar under it where we choose the beginning of the clip and the end of the clip
    * When click on the seeker bar we should seek to the clicked time in the video
    * Each clip will become a new video in the video bank

IMPORTANT ! If you see anything in the list of features that is unclear please ask question.
IMPORTANT ! If you think something is a must have you should add it

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

