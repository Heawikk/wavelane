import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The words of the song that is playing.

    Synced lyrics are followed line by line: the sung line is highlighted and
    kept in the middle. The listener can scroll away to read ahead or behind;
    after five idle seconds the view returns to the sung line on its own, and
    clicking a line rewinds the song to it. Plain lyrics are just text to scroll.
*/
Rectangle {
    id: root

    color: Theme.bg

    signal editRequested()
    signal closeRequested()

    //! How long the listener may be left alone before the view returns to the song.
    property int returnDelayMs: 5000

    readonly property bool synced: lyrics.state === "synced"
    readonly property bool hasLines: (lyrics.state === "synced" || lyrics.state === "plain")
                                     && lyrics.lines.length > 0
    //! False while the listener has scrolled away from the sung line.
    property bool following: true

    // ---------------------------------------------------------------- scrolling
    //! The line (or text) centred in the view, in content coordinates.
    function targetFor(index) {
        if (index < 0 || index >= lineRepeater.count)
            return 0
        const item = lineRepeater.itemAt(index)
        if (!item)
            return 0
        const centre = column.y + item.y + item.height / 2
        return Math.max(0, Math.min(centre - flick.height / 2,
                                    Math.max(0, flick.contentHeight - flick.height)))
    }

    function scrollTo(y, animated) {
        scrollAnimation.stop()
        if (animated && Math.abs(flick.contentY - y) > 1) {
            scrollAnimation.to = y
            scrollAnimation.start()
        } else {
            flick.contentY = y
        }
    }

    function followSong(animated) {
        if (!synced)
            return
        root.following = true
        returnTimer.stop()
        scrollTo(targetFor(lyrics.activeIndex), animated)
    }

    //! The listener took the view into their own hands.
    function userScrolled() {
        if (!synced)
            return
        scrollAnimation.stop()
        root.following = false
        returnTimer.restart()
    }

    Timer {
        id: returnTimer
        interval: root.returnDelayMs
        onTriggered: {
            // Still dragging the scroll bar or a flick: keep waiting.
            if (flick.dragging || flick.flicking || scrollBar.pressed)
                restart()
            else
                root.followSong(true)
        }
    }

    Connections {
        target: lyrics
        function onActiveIndexChanged() {
            if (root.following)
                root.followSong(true)
        }
        function onLinesChanged() {
            // A different track: start from its beginning, then settle on the sung line.
            root.following = true
            root.scrollTo(0, false)
            Qt.callLater(function() { root.followSong(false) })
        }
    }

    Component.onCompleted: Qt.callLater(function() { root.followSong(false) })

    // ------------------------------------------------------------------ header
    RowLayout {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 28
        anchors.rightMargin: 14
        height: 64
        spacing: 12

        CoverArt {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            visible: player.hasTrack
            coverPath: player.currentTrack.coverPath || ""
            title: player.currentTrack.title || ""
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            Text {
                Layout.fillWidth: true
                text: player.hasTrack ? player.currentTrack.title : ""
                color: Theme.text
                font.family: Theme.sans
                font.pixelSize: Theme.fontBody + 1
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                text: player.hasTrack ? (player.currentTrack.artistName || "") : ""
                color: Theme.muted
                font.family: Theme.sans
                font.pixelSize: Theme.fontSmall
                elide: Text.ElideRight
            }
        }

        Mono {
            visible: root.synced
            text: qsTr("Синхронизирован")
            color: Theme.accentText
        }

        FlatButton {
            visible: auth.isAdmin && player.hasTrack
                     && lyrics.state !== "loading" && lyrics.state !== "error"
            text: lyrics.state === "none" ? qsTr("Добавить текст") : qsTr("Править")
            glyph: Theme.iEdit
            onClicked: root.editRequested()
        }

        IconButton {
            glyph: Theme.iClose
            tooltip: qsTr("Закрыть · Esc")
            onClicked: root.closeRequested()
        }
    }

    Rectangle {
        anchors.top: header.bottom
        width: parent.width
        height: 1
        color: Theme.border
    }

    // ------------------------------------------------------------------- lines
    Flickable {
        id: flick

        anchors.top: header.bottom
        anchors.topMargin: 1
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: root.hasLines
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        contentWidth: width
        // Room above and below so the first and last lines can reach the middle.
        contentHeight: column.height + (root.synced ? height : 80)

        ScrollBar.vertical: FlatScrollBar { id: scrollBar }

        onMovementStarted: root.userScrolled()
        onMovementEnded: if (!root.following) returnTimer.restart()

        // The wheel moves the view by itself; this only notices that it did.
        WheelHandler {
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            blocking: false
            onWheel: root.userScrolled()
        }

        NumberAnimation {
            id: scrollAnimation
            target: flick
            property: "contentY"
            duration: 500
            easing.type: Easing.OutCubic
        }

        Column {
            id: column

            x: Math.max(28, (flick.width - width) / 2)
            y: root.synced ? flick.height / 2 : 32
            width: Math.min(760, flick.width - 56)
            spacing: root.synced ? 6 : 0

            Repeater {
                id: lineRepeater
                model: lyrics.lines

                delegate: Item {
                    id: line

                    required property int index
                    required property var modelData

                    readonly property bool isActive: root.synced && index === lyrics.activeIndex
                    readonly property bool isPast: root.synced && index < lyrics.activeIndex
                    readonly property bool blank: modelData.text === ""
                    readonly property bool clickable: root.synced && modelData.time >= 0

                    width: column.width
                    implicitHeight: label.implicitHeight + (root.synced ? 14 : 0)
                    height: blank && !root.synced ? 18 : implicitHeight

                    Text {
                        id: label

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !(line.blank && !root.synced)
                        text: line.blank ? "· · ·" : line.modelData.text
                        wrapMode: Text.WordWrap
                        font.family: Theme.sans
                        font.pixelSize: root.synced ? 28 : 18
                        font.weight: root.synced ? Font.Bold : Font.Normal
                        lineHeight: root.synced ? 1.1 : 1.4
                        color: {
                            if (!root.synced)
                                return Theme.text
                            if (line.isActive)
                                return Theme.text
                            if (lineMouse.containsMouse && line.clickable)
                                return Theme.muted
                            return line.isPast ? "#40444f" : "#6d7282"
                        }

                        Behavior on color {
                            ColorAnimation { duration: 280 }
                        }
                    }

                    MouseArea {
                        id: lineMouse

                        anchors.fill: parent
                        enabled: line.clickable
                        hoverEnabled: true
                        cursorShape: line.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            player.seek(line.modelData.time)
                            // Go to the chosen line now rather than after the next position tick.
                            root.following = true
                            returnTimer.stop()
                            root.scrollTo(root.targetFor(line.index), true)
                        }
                    }
                }
            }
        }
    }

    // Soft edges, so lines fade in and out rather than being cut off.
    Rectangle {
        visible: root.hasLines
        anchors.top: header.bottom
        anchors.topMargin: 1
        width: parent.width
        height: 48
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.bg }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }
    Rectangle {
        visible: root.hasLines
        anchors.bottom: parent.bottom
        width: parent.width
        height: 64
        gradient: Gradient {
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 1.0; color: Theme.bg }
        }
    }

    // A way back to the sung line once the listener has wandered off.
    FlatButton {
        visible: root.synced && !root.following
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 18
        text: qsTr("К текущей строке")
        glyph: Theme.iChevronDown
        primary: true
        onClicked: root.followSong(true)
    }

    // ------------------------------------------------------- nothing to follow
    ColumnLayout {
        visible: !root.hasLines
        anchors.centerIn: parent
        width: Math.min(parent.width - 56, 420)
        spacing: 12

        BusyIndicator {
            Layout.alignment: Qt.AlignHCenter
            running: lyrics.state === "loading"
            visible: running
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            font.family: Theme.sans
            font.pixelSize: 18
            font.weight: Font.DemiBold
            color: lyrics.state === "loading" ? Theme.faint : Theme.muted
            text: {
                if (!player.hasTrack)
                    return qsTr("Ничего не играет")
                switch (lyrics.state) {
                case "loading": return qsTr("Загружаем текст…")
                case "error":   return qsTr("Не удалось загрузить текст")
                default:        return qsTr("Для этого трека нет текста")
                }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: lyrics.state === "none" && auth.isAdmin && player.hasTrack
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            font.family: Theme.sans
            font.pixelSize: Theme.fontSmall
            color: Theme.faint
            text: qsTr("Вы администратор: текст можно добавить и синхронизировать с музыкой.")
        }

        FlatButton {
            Layout.alignment: Qt.AlignHCenter
            visible: lyrics.state === "error"
            text: qsTr("Повторить")
            glyph: Theme.iRefresh
            onClicked: lyrics.reload()
        }
    }
}
