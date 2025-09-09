# Technischer Blueprint: Interaktiver Chatbot "AImar" als virtueller Product Owner

## Überblick und Ziele

Der Chatbot AImar soll in die bestehende Produktentwicklungsplattform integriert werden, um als virtueller Product Owner zu agieren. AImar führt Nutzer:innen schrittweise durch den Prozess der Erstellung eines Product Requirements Document (PRD) und stellt sicher, dass Anforderungen klar, testbar und auf Business-Ziele ausgerichtet sind. Er reagiert professionell, kritisch und motivierend (kein flapsiger Ton, kein Zynismus) und behält den Gesprächskontext über mehrere Interaktionen hinweg. Dadurch kann AImar aktiv Feedback geben – etwa Lücken im PRD aufzeigen, widersprüchliche Ziele markieren oder fehlende Akzeptanzkriterien vorschlagen – und Nutzer:innen bei der Zielfindung, Feature-Aufteilung und Abhängigkeitsanalyse beraten. Die Implementierung erfolgt mit dem bestehenden technologischen Stack (FastAPI, React 18, Tailwind, Celery, Neo4j, Postgres, Qdrant) und bindet sich nahtlos in das vorhandene Agentensystem (ProductOwner, Planner, Architect etc.) ein.

## Architekturkomponenten und Integration

AImar erweitert die Microservice-Architektur der Plattform um spezialisierte Chat-Komponenten in Frontend und Backend. Die folgende Übersicht zeigt die neuen und bestehenden Komponenten sowie deren Zusammenspiel:

```mermaid
flowchart LR
    subgraph Frontend
        UI[Chat UI<br/>(React + ShadCN)]
    end
    subgraph Backend
        API[Chat API (FastAPI)]
        Agent[Product Owner Agent<br/>(LLM + Logik)]
        Memory[(Postgres & Qdrant<br/>Kontextstore)]
        Orchestrator[Orchestrator & Agents<br/>(Planner, Architect,...)]
    end
    UI -- Nutzerfrage --> API
    API -- Kontext abrufen --> Memory
    API -- Aufruf --> Agent
    Agent -- LLM-Anfrage & Analyse --> API
    API -- Antwort zurück --> UI
    API -- (Optional) Folgetasks --> Orchestrator
    Orchestrator -- nutzt Daten --> Memory
```

Diagramm: Architektur und Datenfluss von AImar. Das Frontend beinhaltet eine Chat-UI, die über das Backend (FastAPI) mit dem LLM-gestützten Product-Owner-Agenten kommuniziert. Der Chat API-Layer verwaltet die Konversationslogik, ruft vergangene Chat-Kontexte aus der Datenbank/Memory ab und delegiert inhaltsbezogene Anfragen an den LLM (OpenAI via vorhandene llm_client). Das Memory besteht aus relationalen Tabellen (PostgreSQL) für Chat-Verlauf und Status sowie dem Vektorstore (Qdrant) für semantische Langzeitkontexte. Der Chatbot greift bei Bedarf auf bestehende Agenten zurück – z. B. kann er über den Orchestrator den Planner oder Architect Agent einspannen, sobald das PRD final ist, um die weiteren Schritte (Architektur-Blueprint, Task-Planung) anzustoßen. Dadurch fügt sich AImar in die End-to-End-Pipeline ein, die bereits Tasks in Neo4j verwaltet und über Celery-Worker ausführt.

## LLM-Anbindung

AImar nutzt denselben LLM-Service wie die bisherigen Agenten (OpenAI GPT-Modelle über `chat_with_tools` im `llm_client`). Eine spezielle Prompt-Vorlage für den Product-Owner-Dialog stellt sicher, dass AImar in professionellem Ton antwortet und alle gewünschten Funktionen (Feedback geben, Fragen stellen, Vorschläge machen) erfüllt. Dank optionaler Tool-Unterstützung kann der Agent bei Bedarf Hilfsmittel nutzen (z. B. Wissenssuche via `deep_research`, bereits im Architect-Agent vorhanden). Die Temperatur wird moderat gehalten (z. B. 0.2), um konsistente, deterministische Rückmeldungen wie geforderte Kritik oder Lob zu gewährleisten. Wichtig ist, dass AImar bei jeder Antwort den bisherigen Konversationsverlauf und den Projekthintergrund berücksichtigt – hierzu nutzt er die in der Memory gespeicherten Kontextdaten (siehe nächster Abschnitt).

## Gesprächskontext und mehrteilige Threads

Ein zentrales Feature von AImar ist die Kontextpersistenz über mehrere Threads hinweg. In diesem System entspricht ein Thread in der Regel einem Projektzweck (Purpose) – d. h. jede Produktidee oder jedes Projektziel hat seinen eigenen Chat-Verlauf. Alle Chatnachrichten werden mit einer `purpose_id` verknüpft und in der Datenbank gespeichert, um jederzeit den Bezug zum Projekt herzustellen. Dies spiegelt das bestehende Datenmodell wider, in dem Aufgaben und Artefakte ebenfalls an einen Purpose gekoppelt sind. Wechselt die Nutzer:in zwischen Projekten (Purposes), hat jeder Purpose einen separaten Chatthread mit AImar.

Innerhalb eines Purpose-Threads behält AImar über beliebig viele Nachrichten hinweg den Dialogkontext bei. Zu Beginn eines neuen Projekts ist der Kontext dünn (nur der Projekttitel/Zweck), doch im Verlauf sammelt AImar wichtige Informationen: z. B. die definierte Vision, aufgelistete Features, bereits formulierte Akzeptanzkriterien und identifizierte Unklarheiten. Diese feingranulare Memory wird teils explizit in einer Kontextstruktur gehalten und teils aus früheren Nachrichten on-the-fly abgeleitet. Relevante Kontextelemente – etwa der aktuelle PRD-Entwurf oder offene Fragen – werden im State Store persistiert, z. B. als zuletzt bekannter PRD-Inhalt in einem Artifact oder als separate Zusammenfassungseinträge. Zusätzlich werden längere Dokumentationen (z. B. PRD-Versionen, Blueprint) im Vektor-Index abgelegt, um sie später per semantischer Suche abrufen zu können.

So kann AImar auch kontextübergreifend reagieren: Hat die Nutzer:in z. B. im Thread Aufgabenplanung (nach der PRD-Phase) eine Frage, die auf ein früheres Gespräch im Thread Zieldefinition verweist, kann der Bot mittels vektorbasiertem Similarity Search relevante frühere Aussagen oder Entscheidungen finden und in die Antwort einfließen lassen. Das System `vector_store.query_vectors` wird hierfür mit dem Tenant- und Purpose-Kontext genutzt, ähnlich wie es heute schon für Code- und Artefaktsnippets geschieht.

## Konversationsablauf

Pro Anfrage der Nutzer:in läuft folgendes ab: Die Chat-API holt zunächst die letzten $n$ Nachrichten des Threads aus der DB (oder eine verdichtete Zusammenfassung, falls der Verlauf sehr lang ist) und rekonstruiert damit den Prompt für den LLM. Zusätzlich werden projektbezogene Eckdaten (Projektname, Ziele) und ggf. der aktuelle PRD-Entwurf als Kontext beigefügt. AImar erhält so alle nötigen Informationen, um eine neue Antwort konsistent und kontextbezogen zu generieren. Die neue AI-Antwort wird dann zusammen mit der Nutzereingabe als neue `ChatMessage`-Einträge gespeichert, was den Chatverlauf fortschreibt.

## UI-Design und Nutzererlebnis

Die Benutzeroberfläche wird um eine Chat-Komponente erweitert, die in Next.js/React implementiert ist (unter Nutzung bestehender Patterns in `apps/web`). Wir setzen auf ShadCN UI und Tailwind für konsistente Gestaltung. Geplant ist ein konversationsbasiertes Panel, das entweder in der Pipeline-Ansicht (als ausklappbarer Bereich) oder auf einer eigenen Seite erscheint. Ein möglicher Platz wäre rechts neben dem Aufgaben-Backlog, wo derzeit ein Platzhalter sein könnte. In jedem Fall zeigt die Chat-UI einen Verlauf aller Nachrichten an, mit klarer Kennzeichnung der Rollen:

- **User-Nachrichten:** Vom Menschen eingegebene Beiträge, z. B. Anforderungen oder Antworten auf AImars Fragen. Diese könnten rechtsbündig oder anders stilistisch abgesetzt dargestellt werden (z. B. andere Hintergrundfarbe), inkl. Label "User".
- **AImar-Nachrichten:** Antworten des Chatbots. Sie tragen das Label "AImar" (ggf. mit kleinem Product-Owner-Icon) und werden linksbündig in einer eigenen Sprechblasenfarbe angezeigt. Falls später andere AI-Rollen (Dev, QA) Chats bekommen, würde hier der jeweilige Rollenname stehen.
- **Agent/System-Nachrichten:** In Sonderfällen können auch Systemmeldungen auftauchen, z. B. ein Hinweis "Projekt pausiert" oder "PRD freigegeben – Starte Architektur". Diese werden neutral formatiert und ggf. kursiv angezeigt, um sie von der eigentlichen Unterhaltung abzuheben.

Die Chat-UI unterstützt Markdown-Rendering für die AI-Antworten, damit AImar formatierte Texte (Listen, Hervorhebungen, Tabellen, etc.) und Ausschnitte aus dem PRD übersichtlich darstellen kann. Die bestehende Markdown-Render-Pipeline (ReactMarkdown mit GFM-Erweiterung) wird wiederverwendet, wodurch z. B. Aufzählungen für Feature-Listen oder fett markierte Begriffe direkt korrekt gerendert werden. Ebenso wird AImar Codeblöcke (etwa Pseudocode oder JSON-Beispiele) mit der vorhandenen `<ReactMarkdown>`-Komponente anzeigen lassen.

**Eingabefeld:** Unterhalb des Verlaufs befindet sich ein Textfeld für die Nutzereingabe, mit Sende-Button. Hier können Nutzer:innen frei formulierte Fragen/Anweisungen eingeben („Liste ein weiteres Feature auf…“, „Warum ist Feature X wichtig?“) oder auf Vorschläge von AImar reagieren. Wichtig: Das UI erlaubt auch das Auswählen vordefinierter Feedback-Buttons (siehe nächster Abschnitt), die als Schnellantworten fungieren. Diese Buttons werden inline bei bestimmten AImar-Nachrichten angezeigt. Wenn der:die Nutzer:in darauf klickt, wird entweder eine entsprechende Chat-Nachricht abgesendet (z. B. "Diese Anforderung ist unklar formuliert.") oder ein interner API-Call ausgelöst, je nach Umsetzung.

**Live-Updates:** Um ein responsives Chatgefühl zu erzeugen, wird die Chat-API entweder per WebSocket/SSE angebunden oder mit Polling in kurzen Intervallen (<1s) überwacht. Präferiert wird ein WebSocket-Kanal (`/ws/chat/{purposeId}`), über den das Backend neue AImar-Nachrichten pushen kann, sobald der LLM geantwortet hat. Dies erlaubt perspektivisch auch Streaming der Teilantworten (Token-Streaming), falls die OpenAI-API das unterstützt – für den MVP kann aber auch einfach gewartet und die komplette Antwort am Stück geschickt werden. Die UI zeigt während der Antwortgenerierung einen Ladeindikator (z.B. drei pulsierende Punkte oder "AImar schreibt…"). Nach Empfang scrollt der Verlauf automatisch nach unten.

## API-Design für Chat-Endpunkte

Im Backend wird die FastAPI-Routing-Schicht um dedizierte Chat-Endpunkte erweitert. Diese sind RESTful gehalten, um Einfachheit zu gewährleisten (der bidirektionale Datenstrom bei WebSockets wird optional zusätzlich implementiert). Vorgesehen sind insbesondere:

- **POST `/api/purposes/{purpose_id}/chat/messages`** – Empfängt eine neue Nutzer-Chatnachricht für den gegebenen Purpose. Request-Body ist ein JSON mit dem Text der Nachricht (und optional weiteren Metaangaben). Der Endpoint legt einen neuen `ChatMessage`-Eintrag (Rolle=User) in der DB an, ruft dann die AImar-Logik auf und gibt die AI-Antwort zurück (synchroner Workflow). Die Response enthält die AI-Nachricht (Text + eventuelle Strukturelemente wie Vorschlags-Buttons als maschinenlesbare Daten) sowie ggf. eine Liste neu entstandener Folgemetadaten (z. B. aktualisierte Kontext-Summary).
- **GET `/api/purposes/{purpose_id}/chat/messages`** – Liefert den gesamten bisherigen Chat-Verlauf (oder die letzten n Nachrichten) für einen Purpose als Liste. Dies ermöglicht dem Frontend z.B. beim (Wieder-)Öffnen eines Projekts den bisherigen Dialog anzuzeigen oder bei Verbindungsverlust die Sync zu behalten. Jede Message enthält Felder wie `author` (z.B. "User" oder "AImar"), `content`, `timestamp` und evtl. eine `message_type` falls es besondere Format-Typen gibt (z.B. Systemnachricht).
- **WebSocket `/ws/chat/{purpose_id}`** – (Optional) WebSocket-Kanal, der vom Frontend geöffnet wird, um neue Nachrichten in Echtzeit zu erhalten. Sobald der Nutzer eine Nachricht schickt (via POST wie oben oder als WS-Event), verarbeitet der Server sie und sendet die AI-Antwort als WebSocket-Nachricht zurück. Dieser Mechanismus kann parallel zum HTTP-POST genutzt werden oder diesen ersetzen. In jedem Fall sollte das Protokoll einfach sein (z.B. JSON-Messages mit `role` und `content` Feldern).
- **POST `/api/purposes/{purpose_id}/chat/feedback`** – (Optional, alternativ zu obigem Mechanismus) Ein spezialisierter Endpoint, um vom UI ausgewählte Feedback-Kategorien oder Quick-Reply-Buttons zu verarbeiten. Beispielsweise könnte ein Klick auf „Nicht testbar“ hierhin gemeldet werden, mit Angabe, auf welche Anforderung sich das bezieht. Der Endpoint würde diese Info in eine geeignete Chat-Nachricht oder in ein Feedback-Objekt umwandeln und eine entsprechende AImar-Antwort triggern. Dieses Design kann jedoch auch durch den generischen POST `/chat/messages` abgedeckt werden, indem der Button-Klick als normaler Chat-Text (oder mit einem speziellen Tag) gesendet wird – was die Implementation vereinfacht.

Die API verwendet Pydantic-Modelle zur Validierung und Dokumentation. Beispielsweise definieren wir ein Schema `ChatMessageCreate` (mit Feldern `purpose_id`, `author` (implizit oder vom Token abgeleitet), `content`) für eingehende Nachrichten und `ChatMessageRead` für ausgehende (mit zusätzlichen Feldern wie `id`, `timestamp`). Dieser Trennung von Input- und Output-DTOs folgt dem generellen API-Stil der Plattform (vgl. Tasks/Artifacts API, wo Create/Read-Modelle getrennt sind).

**Transaktionen, Logging und Fehlerfälle:** Die Chat-API überprüft zunächst, ob die Purpose-ID gültig und zum Tenant gehörig ist (ähnlich wie es andere Endpoints tun). Bei Fehlern werden entsprechende HTTP-Fehlercodes und Meldungen zurückgegeben (404 für unbekannten Purpose, 403 falls unberechtigt, etc.). Jede erfolgreiche Interaktion wird in der DB persistiert, sodass kein Zustand nur im Speicher bleibt – dies ist wichtig für Testbarkeit und Skalierung. Zudem kann über Prometheus Metriken erfasst werden (ähnlich wie bereits LLM-Call-Counter existieren, könnte man z.B. `ai_chat_requests_total` und LLM-Token-Verbrauch pro Chat erfassen).

## Datenmodell und Persistenz

Für die Chat-Erweiterung sind neue Tabellen/Modelle im relationalen Schema erforderlich. Aufbauend auf SQLModel (wie im bestehenden Modell genutzt) werden wir z.B. folgende Klassen definieren:

### `ChatMessage` (SQLModel)

Repräsentiert eine einzelne Chat-Nachricht. Wichtige Felder:

- `id` (Primärschlüssel, z.B. UUID8 wie bei anderen Objekten),
- `purpose_id` (ForeignKey → `Purpose.id`, ordnet Nachricht einem Projekt zu),
- `author` (Enum oder str: "User", "AImar", ggf. "System"),
- `content` (Text der Nachricht, Markdown-fähig),
- `created_at` (Timestamp).

Optional: Verweise auf Kontextobjekte wie `artifact_id` oder `task_id`, falls eine Nachricht sich auf ein bestimmtes Artefakt bezieht (z.B. AImar zitiert einen PRD-Ausschnitt – dann kann `artifact_id` auf das PRD-Artifact zeigen). Über diese Foreign Keys kann man Kontext schnell nachladen. Die Beziehung `Purpose.chat_messages` (`back_populates`) erlaubt außerdem einfache Abfragen aller Nachrichten eines Projekts.

### `ThreadContext` / `ChatThread` (SQLModel)

Dieses Modell dient als Metadaten-Container pro Chat-Thread (also i.d.R. pro Purpose und AI-Rolle). Da im MVP nur der Product Owner Chat existiert und 1:1 mit Purpose zusammenfällt, könnte dieses Modell optional sein; es wird aber für Erweiterbarkeit auf mehrere parallele Chats pro Purpose nützlich. Felder:

- `purpose_id` + `agent_role` könnten den Primary Key zusammen bilden (oder eine separate ID mit unique constraint auf Kombi),
- ggf. ein `summary` Feld (Textzusammenfassung des bisherigen Chats, die regelmäßig aktualisiert wird, um Konversationen zu verlängern ohne Kontextverlust),
- evtl. Flags wie `is_active` oder `last_active_at`.

In einer künftigen Version könnte man hier auch ein vektorisiertes Memory-Snapshot ablegen oder Pointer auf wichtige Kontext-Anchor (z.B. "aktuelles PRD Artifact ID").

### `FeedbackTemplate` (SQLModel oder Enum)

Um die Feedback-Vorlagen zu verwalten, die AImar anbieten kann, definieren wir eine kleine Struktur für diese Kategorien. Dies könnte als einfache Enum-Klasse reichen (`FeedbackCategory` mit Werten wie `UNCLEAR`, `NOT_TESTABLE`, `NO_BUSINESS_GOAL`). Alternativ als Tabelle: `FeedbackTemplate` mit Feldern `id` (Name/Slug), `message` (Kurztext für Button, z.B. "Klingt unklar") und `description` (längere Beschreibung oder Hilfetext). Da diese Kategorien relativ statisch sind, reicht vermutlich eine Enum und eine Mapping im Code, aber ein DB-gestütztes Modell böte die Möglichkeit, diese Kategorien dynamisch zu konfigurieren oder zu internationalisieren.

### Artifact & ArtifactFeedback

Diese bleiben bestehen wie im aktuellen Modell. Allerdings wird AImar eng damit verzahnt: Das PRD selbst liegt ja als Markdown-Artifact in der Datenbank (Pfad `requirements/product_requirements.md`). Änderungen am PRD-Text geschehen nicht direkt durch Editieren dieses Artefakts, sondern gesteuert über Feedback und Chat. Bereits jetzt gibt es die `ArtifactFeedback`-Tabelle, die Feedback-Einträge versioniert auf Artefakte speichert. Diese nutzen wir im Hintergrund weiter: Wenn AImar im Chat das PRD inhaltlich ändert, erzeugt er einen neuen Artefaktstand (via `save_artefact` Overwrite) und loggt eine Feedback-Notiz. In der Chat-Konversation kann er die Änderung dem User mitteilen („Ich habe das PRD aktualisiert.“) – technisch gesehen passiert ähnliches schon jetzt, wo nach Feedback ein AI-Antwort-Feedback gespeichert wird. Diese Doppelspeicherung (ChatMessage und ArtifactFeedback) mag redundant wirken, garantiert aber, dass sowohl der Chatverlauf vollständig ist als auch die Artefakt-Historie auditiert wird.

Zur Persistenz: Alle neuen Models werden mit Alembic-Migrationen angelegt. ChatMessage-Records wachsen potenziell mit jeder Unterhaltung; hierauf müssen Indexe für `purpose_id` gelegt werden, um schnelle Abfragen pro Thread zu erlauben. Für `ThreadContext` genügt ein paar Dutzend Zeilen pro Purpose. Langfristige Konversationshistorie könnte optional archiviert oder vektorisiert werden, sollte aber dank schlanker Textnachrichten keine unmittelbaren Speicherprobleme verursachen (im Vergleich zu Code-Artefakten). Wichtig ist auch, dass wir in Qdrant eine separate Collection oder zusätzliche Payload-Filter für Chat-Einträge verwenden, um kontextrelevante Suchen zu ermöglichen (z.B. `metadata={'type': 'chat_message', 'purpose': X}`). Der vorhandene VectorStore ist generisch auf Artefakte ausgelegt – hier kann AImar bei Bedarf z.B. das gesamte PRD oder wichtige Chatpassagen als virtuelles Artefakt einbetten, was über das bestehende Interface (`Artefact` mit `repo_path` "memory/chat_X.md") realisiert werden könnte.

## Feedback-Mechanismus und Qualitätsprüfung

Ein Alleinstellungsmerkmal von AImar ist das proaktive Feedback auf Nutzereingaben im PRD-Prozess. Dies wird durch eine Kombination aus Prompt-Engineering und Regelwerken erreicht:

**LLM-Evaluierung:** Im Prompt von AImar wird verankert, dass er jede neue Anforderung oder Änderung prüfen soll: Ist sie klar formuliert? Ist sie spezifisch und testbar? Passt sie zum übergeordneten Ziel? Fehlen Akzeptanzkriterien? Etc. Basierend auf diesen Kriterien kann AImar seine Antwort strukturieren. Zum Beispiel könnte eine Nutzeranforderung "Die App soll modern aussehen" folgende Reaktion auslösen:

1. AImar lobt ggf. das Ziel (Professioneller Ton: "Ein modernes Erscheinungsbild ist wichtig, verstanden."),
2. Merkt aber an, dass es unpräzise ist ("Allerdings klingt das noch etwas unklar"),
3. und nicht direkt testbar ("und es ist schwer, daraus konkrete Tests abzuleiten"),
4. Dann schlägt er vor, es genauer zu machen ("Möchten Sie 'modern' durch konkrete UI-Richtlinien oder Beispiele ersetzen?").

Dabei werden ein oder mehrere Feedback-Vorschläge als Buttons angeboten, z.B. `[Klingt unklar]`, `[Nicht testbar]`, vielleicht `[Fehlt Akzeptanzkriterium]`. Diese Buttons sind Kurzlabels für die erkannte Problemkategorie. Die Nutzer:in kann auf einen oder mehrere klicken – was dem System signalisiert, welche Richtung gewünscht ist.

**Button-Interaktion:** Angenommen, der:die Nutzer:in klickt auf "Klingt unklar". Die UI könnte daraufhin entweder eine vordefinierte Chat-Nachricht an AImar schicken wie "Das war mir noch unklar." oder direkt intern einen Parameter setzen. Im einfachsten Fall behandeln wir den Klick wie eine Nutzer-Nachricht, auf die AImar wiederum reagiert, z.B. mit einer vertiefenden Frage: "Alles klar. Was genau meinst du mit 'modern'? Gibt es Beispiele oder bestimmte Designs, die dir vorschweben?". Entsprechend würde ein Klick auf "Nicht testbar" AImar veranlassen, auf Überprüfbarkeit einzugehen: "Guter Punkt – um es testbar zu machen, könnten wir ein messbares Kriterium festlegen. Sollen wir z.B. eine Ladezeit oder UX-Metrik definieren?". Durch diese Schleifen stellt AImar sicher, dass am Ende jede Anforderung präzisiert und mit greifbaren Kriterien versehen wird.

Die Kategorien der Feedback-Vorlagen entsprechen typischen Qualitätskriterien für Anforderungen (angelehnt an z.B. INVEST-Regeln):

- Unklar formuliert,
- Zu allgemein/umfangreich,
- Nicht testbar,
- Kein Business-Ziel ersichtlich,
- Widersprüchlich zu… etc.

Im MVP sind konkret die im Prompt genannten Beispiele zu implementieren: „Klingt unklar“, „Nicht testbar“, „Fehlt Business-Ziel“. Intern mappt AImar diese Labels auf Erklärungen: "unklar" bedeutet fehlende Spezifizität, "nicht testbar" bedeutet keine klaren Erfolgskriterien, "fehlt Business-Ziel" bedeutet der Nutzen für das Geschäfts- oder Produktziel ist nicht erkennbar. Diese Erläuterungen kann er dem Nutzer auch direkt liefern, um edukativ zu wirken.

Die Umsetzung im Code kann wie folgt aussehen: Nachdem der LLM die Nutzeranforderung analysiert hat, gibt er strukturiert zurück, welche Kategorien zutreffen. Dies könnte z.B. durch ein Zwischenformat (JSON) erfolgen, das AImar dann in eine natürlichsprachliche Antwort umformt. Oder man nutzt die eingebaute Fähigkeit, mittels OpenAI-Function-Calling eine `validate_requirement` Funktion aufzurufen, die die Kategorien zurückgibt. Für den ersten Wurf reicht jedoch ein entsprechend gestalteter Prompt, der die Antwort von AImar immer nach dem Muster gliedert:

1. Kurze inhaltliche Antwort,
2. Feedback-Hinweis im Satz,
3. Vorschlag mit Buttons.

Im UI wird ein spezieller Parser dafür sorgen, dass erkannte Button-Tags (z.B. via Platzhalter oder markdown-Like `[Option](#action=id)`) in echte klickbare Buttons umgewandelt werden. Diese rufen dann den oben beschriebenen Mechanismus (Follow-up Chat-Nachricht) auf.

Zudem kann AImar Vorschläge initiieren: Etwa nachdem mehrere Anforderungen gesammelt wurden, könnte er fragen "Möchtest du für Feature X Akzeptanzkriterien formulieren?". Solche Vorschläge können ebenfalls als Button "Akzeptanzkriterium hinzufügen" auftauchen. Hier würde der Klick schlicht bedeuten, dass die Nutzer:in zustimmt – worauf AImar einen entsprechenden Prompt stellt ("Okay, was wäre ein denkbares Kriterium, um den Erfolg von Feature X zu prüfen?").

### Zusammenspiel mit PRD-Dokument

AImar kann das wachsende PRD dokumentieren und dem User Ausschnitte daraus zeigen. Z.B. wenn das PRD bereits eine Sektion "Features" mit Einträgen hat, könnte AImar in seiner Nachricht eine Zusammenfassung oder Nummerierung dieser Features einblenden, um den Kontext zu halten. Durch Markdown-Rendering können diese Abschnitte formatiert dargestellt werden, und AImar kann auch To-Do-Listen einführen (etwa: "Offene Punkte: ..."). Solche offenen Punkte könnten dann entweder per Chat oder über das vorhandene Feedback-Form beantwortet werden. Tatsächlich gab es bisher die Lösung, offene Fragen in den Artefakttext zu schreiben (z.B. "Open Questions" Liste im PRD), welche der User in der UI beantworten konnte. Mit AImar könnte man viele dieser Q&A-Schritte in die Konversation verlagern – interaktiver und geführter. Dennoch werden wir die ArtifactFeedback-Formular-Funktion nicht entfernen: wenn AImar z.B. am Ende des PRD noch ungelöste Fragen belässt, tauchen diese wie gehabt in der UI auf und können schriftlich beantwortet werden. Diese Antworten fließen dann wieder über den `/artifacts/{id}/feedback` Endpoint ins System und AImar verarbeitet sie – analog zu jetzt, wo `run_requirements_feedback` aufgerufen wird, um basierend auf Antworten das PRD zu aktualisieren.

## Orchestrierung und Systemintegration

Sobald das PRD hinreichend ausgearbeitet ist, soll der Übergang zur automatischen Pipeline (Architekturplanung, Task-Generierung etc.) nahtlos erfolgen. Hierzu wird AImar in das bestehende State- und Freigabe-System eingebunden:

**Pause/Resume Mechanismus:** Standardmäßig wird ein neu angelegtes Projekt zunächst pausiert, bis das PRD fertig ist. Bisher geschah dies implizit, indem das System auf eine Freigabe des PRD wartete (die UI zeigte einen "Pause" Indikator, solange kein Architektur-Artifact vorlag). Mit AImar kann das Initial-Pausieren expliziter gestaltet werden: Nach `create_purpose` wird für diesen Purpose ein Pause-Flag in Redis gesetzt (z.B. `pause:{tenant}:{purpose}=1` wie teils schon vorgesehen). AImar informiert den Nutzer beim Start des Chats darüber: "Ich habe ein leeres PRD erstellt und die automatische Planung pausiert, bis wir hier fertig sind." Ist die Nutzer:in der Meinung, das PRD sei ausformuliert und abgestimmt, kann sie entweder explizit sagen "PRD ist fertig, bitte fortfahren." oder den in der UI vorgesehenen Freigeben-Button klicken. Beide Aktionen führen letztlich zum Aufruf von `POST /api/artifacts/{id}/approve`. Dieser Endpoint markiert das PRD-Artifact als `released=True` und stößt direkt die nächsten Schritte an: Architect und Planner Agent ausführen. In der aktuellen Implementierung wird im Approve-Handler `run_architect` aufgerufen, um synchron das Architektur-Blueprint (Markdown) zu erzeugen, als Artifact zu speichern, dann `run_planner` für die Task-Liste, Tasks in der DB angelegt und schließlich der Neo4j-Graph via ingest aktualisiert. Anschließend wird der Pause-Flag gelöscht, sodass die Pipeline im Frontend weiterläuft (Graph wird sichtbar, Tasks auf todo etc.).

**AImar und Freigabe:** Der Chatbot selbst wird diesen Übergang moderieren. Er könnte z.B. nach Durchgehen aller Features sagen "Ich denke, das PRD sieht gut aus. Bist du bereit für den nächsten Schritt (Architektur & Planung)?" und einen Button "PRD freigeben" anbieten. Klickt der User, könnte entweder direkt im Frontend der `/approve`-API-Call erfolgen (und AImar bekommt ein Signal, dass er Erfolg melden kann), oder der Klick wird als Chat-Nachricht "PRD freigeben" interpretiert, worauf das Backend den Approve-Call intern ausführt und AImar dann antwortet "Alles klar, ich übergebe an den Architect...". In jedem Fall wird im Chat-Verlauf ersichtlich sein, dass die Phase wechselt – man kann eine Systemnachricht hinzufügen à la "*[System] PRD freigegeben.** Architektur-Agent wird gestartet...". Im UI wechselt der Status-Indikator von "🕓 PRD in Arbeit" zu "✅ PRD abgeschlossen" und kurz darauf taucht das Architecture-Artifact und die Task-Liste auf.

**Anbindung der anderen Agenten:** Während der Chatphase ruft AImar primär den LLM mit seinem speziellen Prompt an. Aber konzeptuell kann er auch die bereits vorhandenen Agenten-Funktionen nutzen. Zwei Strategien bieten sich an: (1) Direct LLM – AImar kann alles per Prompt erledigen (auch z.B. eine Beispiel-Taskliste entwerfen, wenn der Nutzer das verlangt). (2) Tool-Use über Orchestrator – AImar hat sozusagen "Fähigkeiten", die bestehenden Agentenlogiken zu verwenden. Beispielsweise könnte AImar intern den Planner-Agent (oder dessen Kernel, `run_planner`) aufrufen, wenn die Nutzer:in fragt "Kannst du die Features in Aufgaben herunterbrechen?". Da `run_planner` eine deterministische, JSON-basierte Aufgabengenerierung macht, könnte AImar dessen Ergebnis aufbereitet im Chat präsentieren (evtl. in einer Markdown-Tabelle mit Task, Abhängigkeit, Business Value). Ähnlich könnte AImar den Architect-Agent mit Web-Recherche füttern, falls der User nach Best Practices fragt. Diese Orchestrierung ist ambitioniert, aber dank der vorhandenen modularen Funktionen erreichbar. In der ersten Version werden wir uns jedoch darauf konzentrieren, dass AImar hauptsächlich als Conversational Layer fungiert und die eigentliche Automation erst nach Freigabe startet (wie gehabt).

**State-Handling:** Da AImar im Chat quasi den Produktdefinitions-Status abbildet, muss der State zwischen Chat und Pipeline synchron bleiben. Konkret: Solange das Projekt pausiert ist, läuft der Chat. Sobald freigegeben und die Pipeline weiterläuft, endet die aktive Chat-Sitzung (oder wechselt den Kontext: AImar könnte danach noch verfügbar sein für Rückfragen, aber sein Hauptjob ist erledigt). Wir modellieren dies so, dass im `ThreadContext` ein Status stehen könnte wie `active_until_release`. Nach Release könnte der Chat-Thread geschlossen oder als read-only Archiv betrachtet werden. Alternativ bleibt er offen, aber AImar würde dann eher Fragen beantworten wie ein Support-Agent, während die Entwicklung läuft (Out of scope für jetzt). Im MVP kann man den Chat nach Freigabe einfrieren und evtl. einen neuen Threadtyp "AI Dev Support" in Zukunft starten. Die UI sollte eindeutig machen, dass nach Freigabe AImar die Kontrolle an die Umsetzung übergibt.

## Testbarkeit und Qualitätssicherung

Beim Design von AImar wurde auf Testbarkeit geachtet. Sowohl Unit-Tests als auch Integrationstests sollen sicherstellen, dass der Chatbot erwartungsgemäß funktioniert:

**Unit-Tests für Logik:** Viele Komponenten der Chatlogik (z.B. Kontexthandling, das Parsen von Buttons, die Formatierung der LLM-Prompts) können unabhängig vom echten LLM getestet werden. Dazu werden Mock-LLM-Implementationen verwendet (ähnlich wie in bestehenden Tests die OpenAI-API durch Stubs ersetzt wird). Beispielsweise kann man `llm_client.chat_with_tools` mocken, um sofort eine vordefinierte Antwort zu liefern, und dann prüfen, ob die Chat-API diese korrekt in `ChatMessage`-Objekte umwandelt und zurückgibt. Auch der Feedback-Kategorisierungs-Code lässt sich deterministisch testen: Gibt die Funktion bei einem bestimmten Eingabesatz die erwarteten Kategorien zurück? etc.

**API-Tests:** Mit FastAPI’s `TestClient` werden End-to-End die neuen Endpoints geprüft. Ein Test kann z.B. einen Dummy-Purpose anlegen, dann einen `POST /chat/messages` mit einem Beispieltext durchführen und überprüfen, dass im Response eine sinnvolle Antwort steht und dass die DB einen `ChatMessage`-Eintrag hat. Auch der WebSocket kann in Tests verbunden werden (Starlette unterstützt WebSocket tests), um sicherzustellen, dass Streaming funktioniert. Die Testumgebung wird mit einer in-memory SQLite und stubbed external services laufen, wie es im Projekt bereits praktiziert wird. Wir können uns an `test_artifact_feedback.py` orientieren, wo ein künstlicher Tenant, Task und Artifact erstellt und dann Feedback-POSTs und Approve durchgespielt werden. Ähnliches machen wir für Chat: künstliche ChatMessages posten und abrufen, inkl. Kette bis zur Freigabe.

**Integrationstests im Ablauf:** Darüber hinaus planen wir einen Szenariotest, der den gesamten PRD-Erstellungsablauf simuliert. Dieser Test könnte folgendermaßen aussehen:

1. Projekt anlegen: via `POST /purposes` (ggf. stubbe LLM-Ausgaben für `run_requirements`).
2. Chat durchführen: Mehrere `POST /chat/messages` mit vorbereiteten Antworten (hier würde man den LLM stubben, um z.B. vorgefertigte AImar-Antworten zu liefern, die verschiedene Buttons enthalten).
3. Buttons simulieren: Diese sind entweder extra Aufrufe oder spezielle Nachrichten.
4. Freigeben: Dann `POST /artifacts/{id}/approve`.
5. Ergebnis prüfen: Es sollten ein Architecture-Artifact und Tasks entstanden sein (über `GET /artifacts` bzw. `/graph` prüfbar), und der Pause-Status sollte false sein.

Dieser Flow kann mithilfe von `TestClient` und eventuell Celery stub (bzw. synchroner Ausführung, was in Approve ja eh synchron implementiert ist) abgebildet werden. Die erwarteten Dokumente (PRD und Blueprint) kann man auf Vorhandensein bestimmter Überschriften prüfen, um sicherzustellen, dass Prompts richtig griffen.

**Komponententests im Frontend:** Der UI-Teil wird ebenfalls testbar gestaltet. Die Chat-Komponente kann z.B. mit Jest/React Testing Library so getestet werden, dass bei Eingabe eines Textes und Klick auf "Senden" die richtigen API-Aufrufe passieren (hier würden wir API-Aufrufe mocken und die Komponente isoliert rendern). Auch die Renderlogik der Buttons aus AImars Nachrichten kann über Testdaten geprüft werden: Etwa ein Fake-AImar-Message mit Inhalt und einem speziellen Format, dann schauen ob der Button im DOM erscheint und ob der `onClick` das erwartete auslöst (z.B. dispatch einer Action oder API-Call).

**Lasttest und Token-Budget:** Da AImar den LLM intensiv nutzt, ist die Budgetierung relevant. Unit-Tests können z.B. verifizieren, dass bei Budget-0 keine weiteren Aufrufe erfolgen (`BudgetExceededError` wird gefangen – analog zu bestehenden Mechanismen). In Staging-Umgebung könnte man einen Dummy-LLM einsetzen, um hohe Last durchzuspielen (z.B. 10 gleichzeitige Chats mit je 20 Nachrichten) und monitoren, ob das System (besonders Qdrant-Suche und DB) performt.

Zusammenfassend wird durch diese Maßnahmen gewährleistet, dass AImar robust und zuverlässig arbeitet, bevor er mit echten Nutzern interagiert.

## Erweiterbarkeit für weitere AI-Rollen

Die Architektur von AImar ist bewusst so entworfen, dass in Zukunft weitere virtuelle Rollen integriert werden können. Denkbar sind z.B.:

- **AI-Dev (Entwickler:in):** Ein Chatbot, der Fragen zur Codebasis beantwortet oder Pair-Programming macht. In der bestehenden Plattform gibt es bereits einen Dev-Agent (für Implementierungsaufgaben). Ein interaktiver AI-Dev könnte an die Artefakte (Code) und Logs angebunden werden, um z.B. während der Entwicklung Q&A zu ermöglichen ("Warum schlägt der Build fehl?"). Architektonisch würde man einen separaten ChatThread pro Purpose mit Rolle "Dev" führen. Die Anfragen würden an einen anderen LLM-Prompt laufen, der spezialisiertes Wissen (Programmiersprache, Framework) hat. Durch Verwendung des Vectorstores könnte der Dev-Bot relevante Code-Snippets oder Fehlermeldungen aus der Projekthistorie ziehen und zitieren. Das jetzige Design mit generischem `ChatMessage` und `agent_role` im `ThreadContext` unterstützt das bereits – es müsste nur eine neue UI-Option geben, um in den Dev-Chat zu wechseln.
- **AI-Architect:** Ähnlich könnte ein Architektur-Chatbot Fachfragen zu Architekturentscheidungen beantworten. Etwa könnte der:die Nutzer:in nach Freigabe des PRD noch einen Dialog mit AI-Architect führen, der das erzeugte Architektur-Blueprint erläutert oder Alternativen diskutiert. Dieser Chat würde auf dem Blueprint-Artifact aufbauen und könnte den Architect Agent (`run_architect`) im Hintergrund für tiefergehende Nachfragen verwenden. Auch hier ist dank der Modularität (separater Prompt, eigener Memory) eine Einbindung möglich.
- **AI-QA (Tester:in):** Ein QA-Chatbot könnte mit der:dem Nutzer:in Testpläne oder Akzeptanzkriterien durchgehen. Tatsächlich generiert das System schon automatisch Tests aus dem PRD und Blueprint. Ein QA-Chat könnte vorab dem Product Owner helfen, testbare Kriterien zu erarbeiten (dies überschneidet sich mit AImars Aufgaben) oder nachträglich Testreports erläutern.

Alle diese Erweiterungen profitieren davon, dass wir `ThreadContext` generisch halten und vielleicht ein Feld `agent_role/purpose_id` als kombinierte ID nutzen. So kann z.B. ein `ChatMessage` immer eindeutig zu einem Purpose und einer Rolle gehören. Die Chat-API ließe sich erweitern, indem man z.B. den `role` als Parameter einführt: `POST /purposes/{id}/chat/{role}/messages`. Für den Moment ist `{role}` default "product_owner" (AImar), aber künftig könnte es "dev", "qa" etc. sein. Intern könnte man den Prompt-Context je nach Rolle variieren und auch andere Tools zulassen.

Wichtig ist, dass UI-seitig das Konzept verständlich präsentiert wird: Evtl. ein Tabsystem im Chat-Fenster ("Product Owner Chat", "Dev Chat", ...). In der ersten Version werden wir AImar als einzigen Chatbot ausliefern, aber die Implementierung macht es einfach, weitere Agent-Personas hinzuzufügen, da die Plattform bereits alle nötigen Bausteine (verschiedene Agent-Queues, Prompt-Templates, Tools) besitzt. Jede neue Rolle kann einen eigenen Prompt-Template bekommen (z.B. `dev_assistant.j2`) und bei Bedarf eigene APIs (der Dev-Bot könnte z.B. eine Funktion `get_code(file_path)` aufrufen dürfen, um Code aus dem Repository anzuzeigen).

Durch die solide Architektur – entkoppelte Module, generische Datenmodelle, zentrale Orchestrierung – ist AImar somit nicht nur ein einzelnes Feature, sondern der Startpunkt für eine Familie von AI-Assistenten in der Produktentwicklungsplattform, die jeweils in ihrer Domäne eng mit dem Nutzer zusammenarbeiten und die Effizienz des gesamten Entwicklungsprozesses steigern.

