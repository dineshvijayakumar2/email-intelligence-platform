import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ConfigProvider } from "antd";

// Components
import { Layout } from "./components/layout";
import { Dashboard } from "./pages/dashboard";
import { MailboxList, MailboxCreate, MailboxEdit } from "./pages/mailboxes";
import { MailboxProcess } from "./pages/mailbox-process";
import { EmailList } from "./pages/emails";
import { ProcessingJobs } from "./pages/processing";

import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <ConfigProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/mailboxes" element={<MailboxList />} />
            <Route path="/mailboxes/create" element={<MailboxCreate />} />
            <Route path="/mailboxes/edit/:id" element={<MailboxEdit />} />
            <Route path="/mailboxes/process/:id" element={<MailboxProcess />} />
            <Route path="/emails" element={<EmailList />} />
            <Route path="/processing" element={<ProcessingJobs />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </ConfigProvider>
    </BrowserRouter>
  );
}

export default App;