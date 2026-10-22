import 'dotenv/config';
import nodemailer from 'nodemailer';

const secure = String(process.env.SMTP_SECURE || 'false').toLowerCase() === 'true';

export const transporter = nodemailer.createTransport({
  host: process.env.SMTP_HOST,
  port: Number(process.env.SMTP_PORT || 587),
  secure,
  auth: {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASS,
  },
});

export async function verifyMail() {
  return transporter.verify();
}

export async function sendMail({ to, subject, text, html }) {
  return transporter.sendMail({
    from: process.env.SMTP_FROM,
    to,
    subject,
    text,
    html,
  });
}
