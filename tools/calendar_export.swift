// Dump the next few days of macOS Calendar events as JSON, for the "calendar" layout.
//
// Built and run by epd/events.py (swiftc -O -o .cache/calendar-export tools/calendar_export.swift).
// EventKit reads the Calendar store directly, so it's fast and needs no Calendar.app.
//
//   .cache/calendar-export [days]     # default 7, starting at today's midnight
//
// Permission: the first run asks for Calendar access, and the grant belongs to whatever
// launched it (the terminal, or /usr/bin/osascript under launchd; see epd/events.py).
// Exit 2 = access denied.

import EventKit
import Foundation

let days = CommandLine.arguments.count > 1 ? Int(CommandLine.arguments[1]) ?? 7 : 7
let store = EKEventStore()

// EventKit's completion handler runs on an arbitrary queue; this is a one-shot CLI, so block on it.
var granted = false
let gate = DispatchSemaphore(value: 0)
store.requestFullAccessToEvents { ok, error in
    granted = ok
    if let error { FileHandle.standardError.write("access error: \(error)\n".data(using: .utf8)!) }
    gate.signal()
}
guard gate.wait(timeout: .now() + 120) == .success, granted else {
    FileHandle.standardError.write(
        "Calendar access denied. Grant it under System Settings > Privacy & Security > Calendars.\n"
            .data(using: .utf8)!)
    exit(2)
}

let cal = Calendar.current
let start = cal.startOfDay(for: Date())
let end = cal.date(byAdding: .day, value: days, to: start)!
let events = store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: nil))

// Local wall-clock times without an offset: the renderer works in naive local datetimes.
let fmt = DateFormatter()
fmt.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"

// The owner's reply to an invite: "accepted", "pending", "tentative", "declined", ... ;
// "none" for events that aren't invites (no attendee is the current user), e.g. their own.
func myStatus(_ e: EKEvent) -> String {
    guard let me = e.attendees?.first(where: { $0.isCurrentUser }) else { return "none" }
    switch me.participantStatus {
    case .accepted: return "accepted"
    case .pending: return "pending"
    case .tentative: return "tentative"
    case .declined: return "declined"
    case .delegated: return "delegated"
    case .completed: return "completed"
    case .inProcess: return "in-process"
    default: return "unknown"
    }
}

var items: [[String: Any]] = []
for e in events where e.status != .canceled {
    items.append([
        "title": e.title ?? "(untitled)",
        "calendar": e.calendar?.title ?? "",
        "start": fmt.string(from: e.startDate),
        "end": fmt.string(from: e.endDate),
        "all_day": e.isAllDay,
        "my_status": myStatus(e),
    ])
}

// Every calendar the store knows (including empty ones), so the owner can see what can be included.
let calendars = store.calendars(for: .event).map { ["title": $0.title, "source": $0.source.title] }

let payload: [String: Any] = [
    "generated_at": fmt.string(from: Date()),
    "calendars": calendars,
    "days": days,
    "events": items,
]
let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write("\n".data(using: .utf8)!)
