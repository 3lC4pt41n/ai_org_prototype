import React from "react";

interface Task {
  id: string;
  description: string;
}

const BacklogList: React.FC<{ tasks: Task[] }> = ({ tasks }) => (
  <div className="backlog-list mt-4">
    <h3 className="mb-2 font-semibold">Backlog</h3>
    {tasks.length === 0 ? (
      <p className="text-sm text-gray-500">Keine Aufgaben im Backlog.</p>
    ) : (
      <ul>
        {tasks.map((t) => (
          <li key={t.id} className="text-sm text-gray-700">
            • {t.description}
          </li>
        ))}
      </ul>
    )}
  </div>
);

export default BacklogList;
