# Platform Features Testing Guide
## For Testing Team (Non-Technical)

This guide lists all the features available in the COSI app organized by platform. Each feature is described in simple terms for easy testing.

---

## 📧 **Gmail / Email**

### Reading & Searching Emails
- **Search emails** - Find emails by keywords, sender, date range, or read/unread status
- **Get emails** - Retrieve specific emails by various filters
- **Get email details** - View extra information and context about specific emails
- **List labels** - See all available email labels/folders
- **Download attachments** - Save email attachments to your device

### Sending & Managing Emails
- **Send email** - Send new emails with subject and body
- **Compose email** - Draft a new email
- **Update email** - Mark emails as read/unread, star/unstar, add/remove labels, or delete
- **Create label** - Make new email labels/folders

---

## 📅 **Google Calendar**

### Event Management
- **Create event** - Add new calendar events with title, date, time, and attendees
- **Get event** - View details of a specific calendar event
- **Update event** - Modify existing calendar events
- **Search events** - Find events by keywords or filters
- **Query events** - Search events with specific criteria
- **Get events** - Retrieve multiple calendar events
- **Delete events** - Remove calendar events based on filters
- **Get calendar context** - View additional details about calendar events

---

## 💬 **Slack**

### Channel Management
- **Get channels** - View all available Slack channels
- **Get channel messages** - Read messages from a specific channel
- **Get channel members** - See who's in a channel
- **Create channel** - Make a new Slack channel
- **Invite user to channel** - Add someone to a channel

### Messaging
- **Send Slack message** - Post messages to channels
- **Send direct message (DM)** - Send private messages to users
- **Reply to message** - Respond to an existing message in a thread
- **Pin message** - Pin important messages to a channel
- **Get DM messages** - Read your direct messages

### User Management
- **List users** - See all Slack users
- **Get user info** - View details about a specific user
- **Get Slack context** - Get extra information about Slack messages

---

## 📄 **Google Docs**

### Document Management
- **Get document content** - Read the content of a document
- **Create document** - Make a new Google Doc
- **Update document** - Edit existing documents
- **Delete document** - Remove a document
- **Share document** - Share a document with others

### Search & History
- **Search in document** - Find specific text within a document
- **Query docs** - Search for documents using filters
- **Get docs context** - View extra information about documents
- **Document history** - See version history of documents
- **Search docs by date** - Find documents created/modified on specific dates
- **List docs** - View all available documents
- **Generate doc from link** - Create a document from a URL

---

## 📊 **Google Sheets**

### Sheet Management
- **List sheets** - View all available spreadsheets
- **Create sheet** - Make a new spreadsheet
- **Read sheet data** - View data from a spreadsheet
- **Update sheet data** - Edit spreadsheet cells
- **Clear sheet range** - Delete data from specific cells
- **Share sheet** - Share a spreadsheet with others
- **Search sheets** - Find spreadsheets
- **Sheet history** - View version history

### Sheet Structure
- **Add new tab** - Create a new worksheet within a spreadsheet
- **Delete sheet tab** - Remove a worksheet
- **List sheet info** - Get detailed information about a spreadsheet

### Charts & Pivot Tables
- **Sheet chart metadata** - View chart information
- **Create chart** - Add charts to visualize data
- **Update chart** - Modify existing charts
- **Create pivot table** - Make pivot tables for data analysis

---

## 🎨 **Google Slides**

### Presentation Management
- **List slides** - View all available presentations
- **Share slide deck** - Share a presentation with others
- **Get slide content** - View content of a presentation
- **Get specific slide** - View a single slide from a presentation
- **Extract text from slides** - Get all text from a presentation
- **Search slides** - Find presentations
- **Slide history** - View version history
- **Get slides context** - View extra information about presentations

### Editing Slides
- **Replace text in slides** - Find and replace text
- **Add text box to slide** - Insert text boxes
- **Add slide to presentation** - Create new slides
- **Format text in slides** - Change text formatting (bold, italic, etc.)

---

## 🎯 **Gamma Presentations**

- **Create Gamma presentation** - Generate AI-powered presentations
- **List Gamma themes** - View available presentation themes

---

## 📝 **Notion**

### Page Management
- **List pages** - View all Notion pages
- **Create page** - Make a new Notion page
- **Create parent page** - Create a top-level page
- **Get page content** - Read page content
- **Update page title** - Change page title
- **Delete page** - Remove a page
- **Append block** - Add content blocks to a page

### Database Management
- **List databases** - View all databases
- **Create database** - Make a new database
- **Find or create database** - Search for database or create if it doesn't exist
- **Query database** - Search within a database
- **List parent pages** - View top-level pages

### Search & Comments
- **Search Notion** - Find pages and content
- **Get Notion documents** - Retrieve documents
- **Get Notion comments** - View comments on pages
- **Add Notion comment** - Add comments to pages or blocks
- **Get Notion context** - View extra information about Notion items

### Tasks
- **Add todo** - Create todo items in Notion

---

## ✅ **Trello (Task Management)**

### Board & List Management
- **List task boards** - View all Trello boards
- **List task members** - See board members
- **List task lists** - View all lists in a board
- **Create task list** - Make a new list
- **Create task list by board name** - Create a list using board name
- **Find task list** - Search for a specific list

### Card (Task) Management
- **List task cards** - View all cards/tasks
- **Create task** - Make a new task card
- **Create task by names** - Create task using board/list names
- **Get task** - View task details
- **Update task** - Modify task details
- **Move task** - Move task to different list
- **Delete task** - Remove a task
- **Search tasks** - Find tasks

### Comments
- **Add task comment** - Comment on a task
- **List task comments** - View all comments on a task
- **Update task comment** - Edit a comment
- **Delete task comment** - Remove a comment

### Members & Collaboration
- **Add task members** - Assign people to a task
- **Remove task member** - Unassign someone from a task

### Labels
- **List task board labels** - View all labels on a board
- **Add task label** - Add a label to a task
- **Remove task label** - Remove a label from a task
- **Create board label** - Make a new label for the board
- **Create board label by board name** - Create label using board name
- **Update board label** - Modify a label
- **Update task label** - Change task's labels

### Checklists
- **Create task checklist** - Add a checklist to a task
- **List task checklists** - View all checklists on a task
- **Add task checkitem** - Add an item to a checklist
- **Update task checkitem** - Modify a checklist item
- **Delete task checkitem** - Remove a checklist item

### Attachments & Custom Fields
- **Add task attachment URL** - Attach a link to a task
- **Set task custom field** - Update custom field values

### Context
- **Get Trello context** - View extra information about Trello items

---

## 🔍 **Cross-Platform Features**

### Context Tools
These tools provide additional correlated information across platforms:
- **Email context** - Get related calendar events, docs, slides, Notion pages, Trello cards, and Slack messages for specific emails
- **Calendar context** - Get related emails, docs, slides, Notion pages, Trello cards, and Slack messages for calendar events
- **Docs context** - Get related items for Google Docs
- **Slides context** - Get related items for presentations
- **Notion context** - Get related items for Notion pages
- **Trello context** - Get related items for Trello tasks
- **Slack context** - Get related items for Slack messages

---

## 🧪 **Testing Tips**

### General Testing Approach
1. **Search & Retrieval** - Test finding existing items with various filters
2. **Creation** - Test creating new items with required and optional fields
3. **Updates** - Test modifying existing items
4. **Deletion** - Test removing items
5. **Sharing** - Test collaboration features where available
6. **Context** - Test cross-platform relationships

### Common Test Scenarios
- Search by date ranges (yesterday, last week, specific dates)
- Search by keywords
- Filter by status (read/unread, completed/pending)
- Filter by people (from/to specific users)
- Create items with minimum required fields
- Create items with all optional fields
- Update single fields
- Update multiple fields at once
- Share with single user
- Share with multiple users
- Delete single items
- Delete by filters

### Date Testing
- Use natural language: "yesterday", "last week", "this month"
- Use specific dates: "2024-01-15"
- Use date ranges: "from 2024-01-01 to 2024-01-31"

### Error Testing
- Try invalid IDs
- Try missing required fields
- Try searching with no results
- Try operations without permissions

---

## 📱 **Platform Availability Summary**

| Platform | Search | Create | Update | Delete | Share | Context |
|----------|--------|--------|--------|--------|-------|---------|
| Gmail | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Calendar | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Slack | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| Google Docs | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Google Sheets | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Google Slides | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| Gamma | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Notion | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Trello | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |

---

## 🎯 **Priority Testing Areas**

### High Priority (Most Used Features)
1. Gmail - Search and send emails
2. Calendar - Create and search events
3. Slack - Send messages and read channels
4. Google Docs - Create and search documents
5. Trello - Create and update tasks

### Medium Priority
1. Google Sheets - Create and read data
2. Google Slides - Create and edit presentations
3. Notion - Create pages and databases
4. Context tools - Cross-platform relationships

### Low Priority (Less Frequently Used)
1. Gamma presentations
2. Advanced sheet features (charts, pivot tables)
3. Label management
4. Custom fields

---

## 📋 **Test Case Template**

For each feature, test:
1. **Happy Path** - Normal successful operation
2. **Edge Cases** - Empty fields, maximum values, special characters
3. **Error Cases** - Invalid inputs, missing permissions, network issues
4. **Integration** - How it works with other platform features
5. **Context** - Cross-platform data correlation

---

**Last Updated:** December 19, 2025
**Version:** 1.0






