import React from 'react';
import { FiFolder, FiShare2, FiPlay } from 'react-icons/fi';
import Dialog from '../Layout/Dialog';
import { useStore } from '../../store/useStore';
import { useProject } from '../../store/useProject';

const STEPS = [
  { icon: <FiFolder />, title: 'Откройте код', text: 'Выберите пример слева или загрузите свой .java / .py файл.' },
  { icon: <FiShare2 />, title: 'Смотрите на схему', text: 'Код превращается в блок-схему, а справа видны найденные проблемы и сложность методов.' },
  { icon: <FiPlay />, title: 'Запустите и сравните', text: '«Запустить» выполняет программу, «Сравнить» проверяет, что после правок она работает так же.' },
];

/** First-run explanation of the three-step flow; reopened from the header. */
const Welcome: React.FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) => (
  <Dialog open={open} onClose={onClose} labelledBy="welcome-title" className="welcome">
    <div className="welcome-mark" aria-hidden="true"><span className="logo-mark" /></div>
    <h2 className="welcome-title" id="welcome-title">Java Blueprints</h2>
    <p className="muted welcome-lead">Покажет, как устроена ваша программа, найдёт медленные места и проверит, что улучшения ничего не сломали.</p>
    <ol className="welcome-steps">
      {STEPS.map((s, i) => (
        <li key={i}>
          <span className="welcome-ico" aria-hidden="true">{s.icon}</span>
          <div><b>{s.title}</b><div className="muted">{s.text}</div></div>
        </li>
      ))}
    </ol>
    <div className="modal-actions">
      <button
        className="btn"
        onClick={() => {
          const lang = useStore.getState().language;
          useProject.getState().open(lang === 'python' ? 'examples/analyzer.py' : 'examples/Analyzer.java');
          onClose();
        }}
      >
        Открыть пример
      </button>
      <button className="btn primary" onClick={onClose} autoFocus>Начать</button>
    </div>
  </Dialog>
);

export default Welcome;
