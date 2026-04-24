import "./globals.css";

export const metadata = {
  title: "Notes Toolkit",
  description: "Notes Toolkit workspace",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
