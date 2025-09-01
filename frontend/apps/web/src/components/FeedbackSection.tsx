import React from "react";

interface Task {
  id: string;
  phase: string;
  description: string;
  artifactUrl?: string;
}

const FeedbackSection: React.FC<{ tasks: Task[] }> = ({ tasks }) => (
  <div className="feedback-section">
    <h3 className="mb-2 font-semibold">Feedback</h3>
    {tasks.map((task) => (
      <div key={task.id} className="mb-3">
        <p className="text-sm">
          <strong>{task.phase}:</strong> {task.description}
        </p>
        {task.artifactUrl && (
          <a
            href={task.artifactUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 underline text-sm"
          >
            Artefakt-Vorschau öffnen
          </a>
        )}
        <input
          type="text"
          placeholder="Feedback eingeben..."
          className="mt-1 w-full p-2 border rounded"
        />
      </div>
    ))}
  </div>
);

export default FeedbackSection;

