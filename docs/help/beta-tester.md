---
id: beta-tester
title: BETA-test
---

Do you want to help shape the future of this integration?
By becoming a beta tester, you play an active role in improving functionality, stability, and overall user experience.


::::danger Important recommendations

Beta versions are not guaranteed to be stable. For that reason:
* Do not install beta versions in your production Home Assistant instance
* Use a separate test environment, development instance, or secondary Home Assistant setup
* Expect breaking changes, incomplete features, and temporary limitations

If something breaks, that is part of the process, and also where your contribution is most valuable.
::::


## What it means to be a beta tester

#### As a beta tester, you help by:
* Testing new features before they are officially released
* Identifying bugs, regressions, or unexpected behavior
* Providing feedback and improvement suggestions
* Creating clear and well described GitHub issues
* Following up on reported issues and re testing fixes when needed

Your input directly influences how the integration evolves.


### What we expect from beta testers

You do not need to be a developer, but it helps if you:
* Have basic knowledge of Home Assistant and custom integrations
* Are comfortable reading logs and enabling debug logging
* Can describe problems clearly and provide relevant context
* Are willing to test specific scenarios or edge cases when requested

Being a good beta tester is less about finding problems accidentally and more about testing intentionally.

### How to contribute effectively

To make the beta process productive:
* Always include version numbers and environment details in issues
* Attach logs or error messages when reporting problems
* Describe what you expected to happen versus what actually happened
* Test fixes or new releases and confirm whether issues are resolved

Clear feedback saves time and helps deliver a better integration for everyone.

### Why join?
* Early access to new features
* Direct influence on design and behavior
* A chance to help improve the integration for the entire community
* Collaboration with others who care about quality and reliability

If this sounds like something you want to be part of, you are very welcome to join as a beta tester and help move the integration forward.

---

## Install and prepair for BETA 

### BETA in HACS

To test the latest beta version of the integration, you install it directly through HACS by re downloading the integration and selecting the beta release.

**Step by step**
	1.	Open Home Assistant
	2.	Go to HACS
	3.	Select Integrations F1 Sensor
	4.	Find and open this integration in the list
	5.	Click the three dots in the top right corner
	6.	Select Redownload
	7.	In the version list, choose the latest beta version
	8.	Confirm and complete the installation

**After installation**
* Restart Home Assistant to ensure the beta version is fully loaded
* Verify the installed version under the integration details
* Enable debug logging if you plan to report issues

::::important 
* Beta versions may contain unfinished features or breaking changes
* Do not install beta versions in a production Home Assistant instance
* Always read the release notes before updating, especially for beta releases
::::

### Enable Debug Logging

To help with troubleshooting and bug reporting, you may be asked to enable debug logging for the integration. This makes it easier to understand what happens internally and to identify issues.

Add the following to your ```configuration.yaml```
```yaml
logger:
  default: warning
  logs:
    custom_components.f1_sensor: debug
```

After enabling debug logging
* Reproduce the issue you are testing or reporting
* Open Settings → System → Logs
* Press the three dots in rigt top corner and select "Show raw logs"
* Copy relevant log entries related to f1_sensor

![Show Raw logs](/img/raw_logs.png)

When creating a GitHub issue, include:
* What you were doing when the issue occurred
* What you expected to happen
* Relevant debug log output


:::important
Debug logging can generate a lot of log data. Disable debug logging once you are done testing to keep logs clean
::::


---

## Enable Development (Replay) Mode

Development mode allows you to run the integration in a replay environment using recorded live timing data. This is primarily intended for development, debugging, and beta testing, without relying on an active Formula 1 session.




### About replay dumps

The replay dump is a real time recording of a live session. This means:
* All timing between events is preserved
* Delays between updates are exactly the same as during the real session
* A full replay can take up to three hours to complete

The replay usually starts with a ```pre``` session phase, where data such as weather and session metadata are updated continuously. When the session goes ```live```, cars begin running and other sensors, such as tyres, laps, and timing, become active.

This makes the replay behavior as close to a real live session as possible and is ideal for testing logic, automations, and UI behavior over time.


### Available replay dumps

Below are example replay dumps from different sessions during the 2025 season that can be used for testing. Each dump represents a specific session and can be replayed independently by updating the replay dump path.

More dumps may be added over time as additional sessions are recorded and prepared for testing.

::::tip Replay dumps 
You can find the Replay dumps **[here](https://github.com/Nicxe/f1_sensor/tree/develop/replay_dumps)**
::::


### How to enable development mode
1.	Open Home Assistant
2.	Go to Settings → Devices & services
3.	Select F1 Sensor
4.	Click Configure
5.	Set Operation mode to Development
6.	Enter the absolute file path to your replay dump in Replay dump path
7.	Submit the form

The integration reloads immediately.

![Development mode](/img/dev_mode.png)


To verify that replay mode is active, check the logs for the message:

```Starting F1 Sensor in development replay mode```

*If the replay dump path is missing, invalid, or unreadable, the integration will automatically fall back to the live SignalR connection.*



---

## Reporting Issues and Providing Feedback

Clear and well structured issue reports are essential for improving the integration. If you encounter a bug, unexpected behavior, or regression, please report it using GitHub Issues.

### Where to report issues

**Bugs, errors, and broken functionality**

Report these in Issues: https://github.com/Nicxe/f1_sensor/issues

**Questions, ideas, and general discussions.**

Use Discussions instead: https://github.com/Nicxe/f1_sensor/discussions/190

:::info PLEASE
Using the correct channel helps keep development focused and efficient.
::::

### How to write a good issue

When creating an issue, be as detailed as possible. A good issue report should include:
* The exact version of the integration
* Your Home Assistant version
* Whether you are running Live or Development (replay) mode
* A clear description of the problem
* What you expected to happen
* What actually happened

#### Logs and diagnostics

Whenever possible, attach:
* Relevant debug logs
* Error messages or stack traces
* Timestamps for when the issue occurred

Logs are often the key to understanding what went wrong.

#### Screenshots and additional context

Screenshots, screen recordings, or UI examples are strongly encouraged when relevant.
They help illustrate issues with:
* Sensor states
* Dashboards
* Timing or visual behavior

Any additional context that helps reproduce the issue is valuable.

#### Follow up and re testing

As a beta tester, you may be asked to:
* Test a proposed fix
* Verify that an issue is resolved in a new release
* Provide feedback on changes or behavior

::::info
Following up on your own issues helps close them faster and improves quality for everyone.
::::


Thank you for helping improve the integration and for taking the time to report issues clearly and thoughtfully.
