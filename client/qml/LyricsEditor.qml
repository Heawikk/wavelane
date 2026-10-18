import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    Administrators write the lyrics of a track here, and time them to the music.

    "Текст" is the text itself: plain, or LRC with a [mm:ss.xx] tag in front of
    each line. "Синхронизация" plays the track and stamps a line with the current
    time at each press of Enter, which writes the tags for you.
*/
Popup {
    id: root

    //! The track being edited, fixed when the editor is opened.
    property string trackId: ""
    property string trackTitle: ""
    property string mode: "text"
    //! The line the next stamp goes to.
    property int cursor: 0

    readonly property int lineCount: syncModel.count
    property int untimed: 0
    //! Something the administrator should know, shown under the text.
    property string message: ""

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    dim: true
    focus: true
    padding: 0
    width: Math.min(880, parent.width - 60)
    height: Math.min(700, parent.height - 60)
    closePolicy: Popup.CloseOnEscape

    Overlay.modal: Rectangle { color: Theme.alpha("#000000", 0.6) }

    background: Rectangle {
        color: Theme.bar
        border.color: Theme.borderStrong
        border.width: 1
    }

    // ----------------------------------------------------------------- helpers
    // [mm:ss.xx] for a time in milliseconds
    function tag(ms) {
        ms = Math.max(0, Math.round(ms))
        const minutes = Math.floor(ms / 60000)
        const seconds = Math.floor((ms % 60000) / 1000)
        const hundredths = Math.floor((ms % 1000) / 10)
        const two = function(n) { return (n < 10 ? "0" : "") + n }
        return "[" + two(minutes) + ":" + two(seconds) + "." + two(hundredths) + "]"
    }

    function clock(ms) {
        return ms < 0 ? "--:--.--" : tag(ms).slice(1, -1)
    }

    // The time of the first [mm:ss.xx] tag of a line, or -1.
    readonly property var timeTag: /^\s*\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]/
    readonly property var anyTag: /\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]/g
    readonly property var metaLine: /^\s*\[[A-Za-z#]+:[^\]]*\]\s*$/

    function parseText(text) {
        const result = []
        const rows = text.replace(/\r/g, "").split("\n")
        for (let i = 0; i < rows.length; ++i) {
            const row = rows[i]
            if (metaLine.test(row))
                continue
            let time = -1
            const match = timeTag.exec(row)
            if (match) {
                const fraction = match[3] ? parseInt((match[3] + "00").slice(0, 3), 10) : 0
                time = (parseInt(match[1], 10) * 60 + parseInt(match[2], 10)) * 1000 + fraction
            }
            const words = row.replace(anyTag, "").replace(/<\d{1,3}:\d{2}(?:[.:]\d{1,3})?>/g, "").trim()
            if (words !== "")
                result.push({ text: words, time: time })
        }
        return result
    }

    // How many lines of the text have no time, when some do (the server drops those).
    function mixedUntimed(text) {
        const rows = parseText(text)
        let timed = 0
        for (let i = 0; i < rows.length; ++i)
            if (rows[i].time >= 0)
                ++timed
        return timed > 0 ? rows.length - timed : 0
    }

    function countUntimed() {
        let missing = 0
        for (let i = 0; i < syncModel.count; ++i)
            if (syncModel.get(i).time < 0)
                ++missing
        root.untimed = missing
    }

    function buildLrc() {
        const rows = []
        for (let i = 0; i < syncModel.count; ++i) {
            const line = syncModel.get(i)
            rows.push((line.time >= 0 ? tag(line.time) : "") + line.text)
        }
        return rows.join("\n")
    }

    function enterSync() {
        const rows = parseText(textArea.text)
        if (rows.length === 0) {
            root.message = qsTr("Сначала впишите текст песни.")
            return
        }
        syncModel.clear()
        for (let i = 0; i < rows.length; ++i)
            syncModel.append(rows[i])
        countUntimed()
        // Continue where the previous session stopped.
        let first = 0
        while (first < syncModel.count && syncModel.get(first).time >= 0)
            ++first
        root.cursor = first < syncModel.count ? first : 0
        root.mode = "sync"
        Qt.callLater(function() {
            syncList.positionViewAtIndex(root.cursor, ListView.Center)
            syncList.forceActiveFocus()
        })
    }

    function leaveSync() {
        textArea.text = buildLrc()
        root.mode = "text"
    }

    function stamp() {
        if (root.cursor >= syncModel.count)
            return
        syncModel.setProperty(root.cursor, "time", player.position)
        root.cursor = Math.min(root.cursor + 1, syncModel.count)
        countUntimed()
        syncList.positionViewAtIndex(Math.min(root.cursor, syncModel.count - 1), ListView.Center)
    }

    function undoStamp() {
        if (root.cursor <= 0 && (root.cursor >= syncModel.count || syncModel.get(0).time < 0))
            return
        root.cursor = Math.max(0, root.cursor - 1)
        const was = syncModel.get(root.cursor).time
        syncModel.setProperty(root.cursor, "time", -1)
        countUntimed()
        // Back to just before where it was, so it can be heard again.
        if (was >= 0)
            player.seek(Math.max(0, was - 2500))
        syncList.positionViewAtIndex(root.cursor, ListView.Center)
    }

    function openForCurrent() {
        if (!player.hasTrack)
            return
        root.trackId = player.currentTrack.id
        root.trackTitle = player.currentTrack.title
        root.mode = "text"
        root.message = ""
        textArea.text = lyrics.trackId === root.trackId ? lyrics.rawText : ""
        open()
        textArea.forceActiveFocus()
    }

    function saveCurrent() {
        const text = root.mode === "sync" ? buildLrc() : textArea.text
        if (text.trim() === "") {
            root.message = qsTr("Текст пустой.")
            return
        }
        lyrics.save(root.trackId, text)
    }

    Connections {
        target: player
        function onCurrentTrackChanged() {
            if (root.opened && player.currentTrack.id !== root.trackId)
                root.close()
        }
    }
    Connections {
        target: lyrics
        function onSaved(id) {
            if (root.opened && id === root.trackId)
                root.close()
        }
    }

    ListModel { id: syncModel }

    ConfirmDialog {
        id: confirmRemove
        heading: qsTr("Удалить текст?")
        message: qsTr("Текст трека «%1» будет удалён для всех слушателей.").arg(root.trackTitle)
        confirmText: qsTr("Удалить")
        danger: true
        onAccepted: lyrics.remove(root.trackId)
    }

    // ------------------------------------------------------------------ layout
    contentItem: ColumnLayout {
        spacing: 0

        SectionHeader {
            Layout.fillWidth: true
            title: qsTr("Текст · %1").arg(root.trackTitle)

            Segmented {
                options: [
                    { value: "text", label: qsTr("Текст") },
                    { value: "sync", label: qsTr("Синхронизация") }
                ]
                current: root.mode
                onPicked: function(value) {
                    if (value === root.mode)
                        return
                    if (value === "sync")
                        root.enterSync()
                    else
                        root.leaveSync()
                }
            }
            IconButton {
                glyph: Theme.iClose
                onClicked: root.close()
            }
        }

        // --- the text itself ---
        ColumnLayout {
            visible: root.mode === "text"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 16
            spacing: 10

            Text {
                Layout.fillWidth: true
                text: qsTr("Вставьте текст песни. Если у строк уже есть метки времени "
                           + "(например, [01:23.45] строка), текст станет синхронизированным; "
                           + "иначе его можно синхронизировать на соседней вкладке.")
                color: Theme.faint
                font.family: Theme.sans
                font.pixelSize: Theme.fontSmall
                wrapMode: Text.WordWrap
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.vertical: FlatScrollBar {}

                TextArea {
                    id: textArea

                    color: Theme.text
                    selectByMouse: true
                    wrapMode: TextEdit.NoWrap
                    leftPadding: 12
                    rightPadding: 12
                    topPadding: 10
                    bottomPadding: 10
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.fontSmall + 1
                    placeholderText: qsTr("Текст песни…")
                    placeholderTextColor: Theme.faint
                    onTextChanged: root.message = ""

                    background: Rectangle {
                        color: Theme.panel
                        border.color: textArea.activeFocus ? Theme.accent : Theme.borderStrong
                        border.width: 1
                    }
                }
            }

            Text {
                id: hint

                // The server keeps only timed lines once any line has a time.
                readonly property int dropped: root.mode === "text" ? root.mixedUntimed(textArea.text) : 0

                Layout.fillWidth: true
                visible: text !== ""
                text: root.message !== "" ? root.message
                      : (dropped > 0 ? qsTr("У %1 строк нет метки времени: при сохранении они будут отброшены.").arg(dropped) : "")
                color: Theme.warning
                font.family: Theme.sans
                font.pixelSize: Theme.fontSmall
                wrapMode: Text.WordWrap
            }
        }

        // --- timing ---
        ColumnLayout {
            visible: root.mode === "sync"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 16
            Layout.bottomMargin: 8
            spacing: 10

            Text {
                Layout.fillWidth: true
                text: qsTr("Включите музыку и нажимайте «Отметить» (Enter) в тот момент, когда "
                           + "начинается строка в рамке. Нажмите на любую строку, чтобы выбрать её "
                           + "заново; «Отменить» (Backspace) возвращает на шаг назад.")
                color: Theme.faint
                font.family: Theme.sans
                font.pixelSize: Theme.fontSmall
                wrapMode: Text.WordWrap
            }

            ListView {
                id: syncList

                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: syncModel
                currentIndex: root.cursor
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: FlatScrollBar {}

                Keys.onReturnPressed: root.stamp()
                Keys.onEnterPressed: root.stamp()
                Keys.onBackPressed: root.undoStamp()
                Keys.onDeletePressed: root.undoStamp()
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Backspace) {
                        root.undoStamp()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Up) {
                        root.cursor = Math.max(0, root.cursor - 1)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Down) {
                        root.cursor = Math.min(syncModel.count - 1, root.cursor + 1)
                        event.accepted = true
                    }
                }

                delegate: Rectangle {
                    id: row

                    required property int index
                    required property string text
                    required property int time

                    readonly property bool isCursor: index === root.cursor

                    width: ListView.view.width
                    height: 34
                    color: isCursor ? Theme.rowSelected : (rowMouse.containsMouse ? Theme.rowHover : "transparent")

                    Rectangle {
                        visible: row.isCursor
                        width: 2
                        height: parent.height
                        color: Theme.accent
                    }

                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        spacing: 14

                        Mono {
                            width: 74
                            height: parent.height
                            text: root.clock(row.time)
                            color: row.time >= 0 ? Theme.accentText : Theme.faint
                            font.capitalization: Font.MixedCase
                        }
                        Text {
                            width: parent.width - 100
                            height: parent.height
                            verticalAlignment: Text.AlignVCenter
                            text: row.text
                            elide: Text.ElideRight
                            color: row.isCursor ? Theme.text : (row.time >= 0 ? Theme.muted : Theme.faint)
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontBody
                        }
                    }

                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            root.cursor = row.index
                            // Let the stamped line be heard again before re-stamping it.
                            if (row.time >= 0)
                                player.seek(Math.max(0, row.time - 2000))
                            syncList.forceActiveFocus()
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                IconButton {
                    size: 32
                    glyph: player.playing ? Theme.iPause : Theme.iPlay
                    glyphSize: 14
                    filled: true
                    tooltip: (player.playing ? qsTr("Пауза") : qsTr("Играть")) + " · Space"
                    onClicked: player.togglePlayPause()
                }
                FlatButton {
                    text: "−5 " + qsTr("с")
                    onClicked: player.seek(Math.max(0, player.position - 5000))
                }
                FlatButton {
                    text: "+5 " + qsTr("с")
                    onClicked: player.seek(player.position + 5000)
                }
                Mono {
                    Layout.leftMargin: 6
                    text: player.positionText + " / " + player.durationText
                    color: Theme.muted
                    font.capitalization: Font.MixedCase
                }

                Item { Layout.fillWidth: true }

                Mono {
                    text: root.untimed > 0 ? qsTr("Без времени: %1").arg(root.untimed)
                                           : qsTr("Все строки отмечены")
                    color: root.untimed > 0 ? Theme.warning : Theme.positive
                }
                FlatButton {
                    text: qsTr("Отменить")
                    enabledWhen: root.cursor > 0 || (root.lineCount > 0 && syncModel.get(0).time >= 0)
                    onClicked: {
                        root.undoStamp()
                        syncList.forceActiveFocus()
                    }
                }
                FlatButton {
                    text: qsTr("Отметить")
                    primary: true
                    enabledWhen: root.cursor < root.lineCount
                    onClicked: {
                        root.stamp()
                        syncList.forceActiveFocus()
                    }
                }
            }
        }

        // --- actions ---
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.border
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 12
            spacing: 8

            FlatButton {
                visible: lyrics.state !== "none" && lyrics.trackId === root.trackId
                text: qsTr("Удалить текст")
                danger: true
                onClicked: confirmRemove.open()
            }

            Item { Layout.fillWidth: true }

            FlatButton {
                text: qsTr("Закрыть")
                onClicked: root.close()
            }
            FlatButton {
                visible: root.mode === "text"
                text: qsTr("Синхронизировать")
                onClicked: root.enterSync()
            }
            FlatButton {
                text: lyrics.saving ? qsTr("Сохраняем…") : qsTr("Сохранить")
                primary: true
                enabledWhen: !lyrics.saving && (root.mode === "text" || root.untimed === 0)
                onClicked: root.saveCurrent()
            }
        }
    }
}
