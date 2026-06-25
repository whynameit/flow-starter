import AppKit
import Foundation

enum PromptError: Error {
    case missing(String)
}

func option(_ name: String, default fallback: String = "") -> String {
    let args = CommandLine.arguments
    for index in 0..<args.count {
        if args[index] == name && index + 1 < args.count {
            return args[index + 1]
        }
    }
    return fallback
}

func flag(_ name: String) -> Bool {
    return CommandLine.arguments.contains(name)
}

func activateApp() {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.activate(ignoringOtherApps: true)
}

func printAndExit(_ text: String, code: Int32 = 0) -> Never {
    FileHandle.standardOutput.write(text.data(using: .utf8) ?? Data())
    exit(code)
}

func blankIcon() -> NSImage {
    let image = NSImage(size: NSSize(width: 1, height: 1))
    image.lockFocus()
    NSColor.clear.set()
    NSRect(x: 0, y: 0, width: 1, height: 1).fill()
    image.unlockFocus()
    return image
}

func plainAlert(title: String, message: String) -> NSAlert {
    let alert = NSAlert()
    alert.messageText = title
    alert.informativeText = message
    alert.alertStyle = .informational
    alert.icon = blankIcon()
    return alert
}

func runTextPrompt() -> Never {
    activateApp()
    let title = option("--title", default: "flow-starter")
    let message = option("--message")
    let defaultText = option("--default")
    let rows = max(1, min(12, Int(option("--rows", default: "3")) ?? 3))

    let alert = plainAlert(title: title, message: message)
    alert.addButton(withTitle: "继续")
    alert.addButton(withTitle: "取消")

    let width: CGFloat = 560
    let height: CGFloat = CGFloat(rows * 24 + 28)
    let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: width, height: height))
    scroll.borderType = .bezelBorder
    scroll.hasVerticalScroller = true
    scroll.autohidesScrollers = false

    let textView = NSTextView(frame: scroll.contentView.bounds)
    textView.string = defaultText
    textView.font = NSFont.systemFont(ofSize: 14)
    textView.isRichText = false
    textView.isVerticallyResizable = true
    textView.isHorizontallyResizable = false
    textView.textContainer?.containerSize = NSSize(width: width, height: CGFloat.greatestFiniteMagnitude)
    textView.textContainer?.widthTracksTextView = true
    textView.autoresizingMask = [.width]
    scroll.documentView = textView
    alert.accessoryView = scroll

    DispatchQueue.main.async {
        textView.window?.makeFirstResponder(textView)
    }

    let response = alert.runModal()
    if response == .alertFirstButtonReturn {
        printAndExit(textView.string)
    }
    printAndExit("", code: 130)
}

func runChoicePrompt() -> Never {
    activateApp()
    let title = option("--title", default: "flow-starter")
    let message = option("--message")
    let rawChoices = option("--choices")
    let defaultChoice = option("--default")
    let choices = rawChoices.split(separator: "|").map(String.init)
    if choices.isEmpty {
        printAndExit("", code: 2)
    }

    let alert = plainAlert(title: title, message: message)
    alert.addButton(withTitle: "继续")
    alert.addButton(withTitle: "取消")

    let popup = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 420, height: 28), pullsDown: false)
    popup.addItems(withTitles: choices)
    if choices.contains(defaultChoice) {
        popup.selectItem(withTitle: defaultChoice)
    }
    alert.accessoryView = popup

    let response = alert.runModal()
    if response == .alertFirstButtonReturn {
        printAndExit(popup.titleOfSelectedItem ?? choices[0])
    }
    printAndExit("", code: 130)
}

func runConfirmPrompt() -> Never {
    activateApp()
    let title = option("--title", default: "flow-starter")
    let message = option("--message")
    let yes = option("--yes", default: "是")
    let no = option("--no", default: "否")

    let alert = plainAlert(title: title, message: message)
    alert.addButton(withTitle: yes)
    alert.addButton(withTitle: no)

    let response = alert.runModal()
    if response == .alertFirstButtonReturn {
        printAndExit("yes")
    }
    printAndExit("no")
}

func runNoticePrompt() -> Never {
    activateApp()
    let title = option("--title", default: "flow-starter")
    let message = option("--message")
    let button = option("--button", default: "好")
    let duration = max(0, Double(option("--duration", default: "0")) ?? 0)

    let alert = plainAlert(title: title, message: message)
    alert.addButton(withTitle: button)

    if duration > 0 {
        DispatchQueue.main.asyncAfter(deadline: .now() + duration) {
            alert.window.close()
            NSApplication.shared.stopModal(withCode: .abort)
        }
    }

    let response = alert.runModal()
    if response == .alertFirstButtonReturn {
        printAndExit("ok")
    }
    printAndExit("timeout")
}

let command = CommandLine.arguments.dropFirst().first ?? ""
switch command {
case "text":
    runTextPrompt()
case "choice":
    runChoicePrompt()
case "confirm":
    runConfirmPrompt()
case "notice":
    runNoticePrompt()
default:
    printAndExit("Usage: flow-starter-prompt text|choice|confirm|notice", code: 2)
}
