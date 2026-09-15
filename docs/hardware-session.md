# Connected setup: 2026-09-15

The first connected session inspected an **OPPO Find X9 Ultra (CPH2841), Android 16** and configured the settings below. These are dated device observations. **A phone alarm sounded clearly with the phone locked, DND active and Bluetooth off. The user also confirmed one incoming alert reached both phone and watch. The full wake-up policy and broader notification tests remain pending.**

The installed-app inventory, confirmed sleep choices, device identifiers, screenshots and detailed change journals remain in ignored `.local/` files. This report includes only selected settings relevant to the notification policy.

## Phone settings read back

| Area | Observed configuration | Verification still needed |
| --- | --- | --- |
| Android inventory | Connected phone and installed notification-permission metadata inspected | Reconnect and scan to detect later changes |
| Weekday wake-up | Existing preparation alarm saved at **10:09 Monday–Friday**, enabled, using the default alarm sound; existing enabled **10:14** reminder preserved | Repeat the alarm test with work quiet hours active to complete the strict policy check |
| Alarm protection | Nonzero alarm volume; DND screen states alarms are unaffected; user confirmed the locked-phone DND test alarm sounded clearly | The completed test ran during work hours, so the work-quiet-hours condition remains untested |
| Discord | Ten categories off: reactions, friend activity, gaming, polls, voice/live activity, forums, events, server messages, other server notifications and stages; **Direct messages** and **Incoming calls** preserved | Confirm wanted DMs/calls arrive; miscellaneous Other and Missed Messages remain mixed or unclear |
| WhatsApp | **Group notifications**, **Chat history backup** and **Group join requests** turned off in Android settings; **Message notifications** remained enabled | Confirm direct messages and calls arrive, and unwanted group/administrative alerts stay quiet |
| Telegram | **Private Chats** remained enabled and call ringtone/vibration settings were preserved; global **Groups**, **Channels**, **Reactions** and **Stories** off; all group/channel notification exceptions removed; **Contact joined Telegram** and **Pinned Messages** off; repeat notifications set to **Never** | Test wanted direct messages/calls and confirm groups, broadcasts, stories and repeat alerts stay quiet |
| Instagram | Eleven social/activity categories off, including likes, follower updates, first posts/stories, highlights and live videos; **Messages**, **Message requests** and **Video calls** preserved | Alerts/Other remain mixed or unknown; Comments, Reminders, Mentions in bio and Posting were not fully reviewed |
| LinkedIn | **Jobs and opportunities**, **Live events**, **Audio rooms** and **News and articles** off; **Invitations and messages** preserved | Invitations share the message category; Other updates remains mixed, and review is partial |
| Picsart | **New Followers**, **Product Announcements**, **Promotions and Special Offers** and **Challenges** off | Mentions, Other and Reminders preserved; review is partial |
| Meetup | No category changed: only **Trial Reminder** and mixed **Other notifications** exposed in the inspected Android settings | In-app review needed to separate direct messages from other alerts |
| Teams reactions | **Likes and reactions** turned off | Confirm reaction alerts are suppressed while wanted chat notifications arrive |
| Teams quiet time | Exact daily quiet interval **18:14–10:14**, plus Saturday and Sunday quiet all day; incoming-call exception retained | Check work messages around the weekday boundaries, a weekend message, and an incoming Teams call |
| Teams desktop duplicates | **When active on other devices** enabled | Compare a message while active on desktop with one after inactivity; test calls separately |
| Outlook work quiet time | Selected **Microsoft 365 work account**: daily **18:14–10:14** quiet hours enabled, plus Saturday and Sunday quiet all day; personal Outlook.com account untouched; **Focused Inbox only** mail notifications preserved | Check work-mail suppression at weekday boundaries and weekends; calendar reminders need separate handling |
| Teams/Outlook sharing | **Set on Teams and Outlook** remained off in each app; matching schedules were configured separately | Recheck each app after a schedule or account change |

The work boundary is **Monday–Friday 10:14–18:14, Europe/Warsaw**. Personal messaging remains separate from Teams quiet time. Confirmed sleep choices are recorded in the private profile; their exact hours are not published here.

Telegram's two Groups exceptions and two Channels exceptions were removed with **Delete All Exceptions**, and neither category showed an exception count afterward. This removed notification overrides only; no chats or messages were deleted. **New Stories** was already off and remained off; **Important Stories** was turned off, leaving the main Stories control off.

In total, **33 Android notification categories** were disabled with before/after readback. Discord's disabled **Messages** category was specifically under **Server**; its separate **Direct messages** category stayed enabled. No whole-app notification permissions were changed. The refreshed inventory at **2026-09-15 15:42:23 UTC** showed all 203 selected permission records unchanged from the initial baseline. Groupon's only observed category was already off; Shazam exposed functional result/player controls, so neither received a change.

### Alarm sound test and cleanup

A temporary alarm fired at **16:56** while the secure keyguard was locked, DND was active (`zen_mode=1`) and Bluetooth was off (`bluetooth_on=0`). The user confirmed it sounded clearly, stopped it and unlocked the phone. The temporary alarm was then deleted and its absence verified; the recurring weekday 10:09 and 10:14 alarms remained enabled.

Bluetooth was restored to on and DND to off. This establishes a passed **locked-phone + DND + Bluetooth-off sound test**. It does not complete `test.wake_alarm`: the test occurred during the work window, so its additional requirement for active work quiet hours remains pending. A native watch alarm, if used, also needs its separate Sleep Focus test.

At session cleanup, the temporary USB keep-awake setting was restored to its original value **0** and verified, returning normal screen-timeout behavior. Final readbacks also confirmed Bluetooth on, DND off and alarm volume unchanged at 12. The phone was returned to its home screen.

### Incoming alert on both devices

Asked to receive a call or direct message, the user confirmed **“Both phone and watch alert.”** This passes one end-to-end incoming-alert check. The exact app and whether the event was a call or message were not specified. It does not establish delivery from every communicator, dismissal synchronization, quiet-hours behavior, Sleep Focus behavior or the full `test.delivery` checklist.

## Garmin Connect settings read back

Garmin Connect identified **fenix 9 Pro - inReach, 51mm**, with firmware **6.38** read from About. Native settings were temporarily blocked by a Not Connected dialog. After Bluetooth was restored following the alarm test, the watch reconnected and native settings became accessible. A sync was requested, and the device list subsequently showed Connected; this does not establish notification delivery.

| Area | Observed configuration | Verification still needed |
| --- | --- | --- |
| Notification access | Enabled for Garmin Connect; watch reconnected after Bluetooth restoration | One incoming alert was confirmed on both devices; test the remaining sources and modes |
| Phone DND behavior | **Follow Do Not Disturb Behavior** changed from off to on | Test allowed notifications with phone DND on and off; do not infer watch focus synchronization |
| Forwarding selection | **All Applications** changed from on to off; **19 specific entries** enabled for calls/direct messages, dedicated work and deliberate alarms | Test a wanted notification from each chosen source and confirm an excluded source stays off the watch |
| List readback | Full App Notifications list traversed; chosen entries enabled and remaining entries off | Recheck after app installation or notification-setting changes |

The phone-side forwarding choices were saved and read back. The complete allowlist and package mapping remain private. The UI had 219 unique app labels and some duplicate labels, so displayed labels alone do not establish a unique Android package identity.

Mixed-purpose apps still need source category or conversation filters. Outlook's selected work account now has the same configured work boundary as Teams; each schedule was saved separately. Their actual quiet-hours behavior remains to be tested. The configured forwarding list does not prove the watch's alert behavior.

## Native watch settings read back

| Area | Observed configuration | Verification still needed |
| --- | --- | --- |
| Calls, texts and apps | Vibration enabled for each | Confirm wanted calls, messages and app notifications reach the watch |
| Existing quiet choices | Daily summary, stress, rest, move, time chimes and connection alerts were already off and remained off | Check normal daily behavior |
| Goal alerts | Changed from on to off | Confirm goal events no longer interrupt |
| Morning and evening reports | Both changed from on to off | Confirm reports remain disabled |
| Sleep schedule | All seven days aligned with the confirmed private phone schedule, including the Saturday extension; each day read back | Verify behavior at sleep boundaries |
| Sleep Focus notifications | **Smart Notifications Status: On** retained | Test the desired alerts while Sleep Focus is active |
| Manual system DND | Off, retained | Check its interaction with phone DND and watch focus modes |

The exact sleep hours remain private. Sleep Focus behavior, native alarm delivery and the broader phone/watch notification tests remain pending. Matching schedules and a Connected label do not verify that alarms or notifications reach either device; the separate user-confirmed incoming alert covers only that one event.

## How these observations relate to the toolkit

Clock, Android category, Telegram, Teams, Outlook and Garmin Connect changes were made through their settings screens, with configuration readback. The CLI's `apply` command only handles supported, explicitly reviewed whole-app Android notification permissions; it does not reproduce the UI changes in this report.

Private desired choices belong in `.local/policy.personal.json`. Detailed configuration observations are in `.local/native-setup.json`, including its `garmin` section; the raw UI evidence stays under `.local/ui/`. The private rules `test.phone_alarm_fallback` and `test.incoming_alert_pair` separately capture the completed alarm test/cleanup and the user-confirmed incoming alert on both devices. Adding a rule does not create an attestation or complete the broader `test.wake_alarm` or `test.delivery` checks. Practical checks must succeed before recording the corresponding `attest ... --result pass`.

Seven scoped passes are now recorded locally: configuration checks for Discord, Teams, WhatsApp, Telegram and the Outlook work schedule, plus the two practical tests above. The broader policy and individual watch-source delivery checks remain pending. The private report was refreshed after recording these checks.

Use the same private policy for later reconciliation:

```powershell
python -m healthier_notifications --policy .local/policy.personal.json plan
python -m healthier_notifications --policy .local/policy.personal.json checks
python -m healthier_notifications --policy .local/policy.personal.json status > .local/status.personal.md
```

Keep `local_only: true` in that profile. Exported public status describes the selected public policy and cannot stand in for the private profile's progress. See the [device guide](device-guide.md) for practical test steps and [README privacy guidance](../README.md#files-and-privacy) before sharing any report.
