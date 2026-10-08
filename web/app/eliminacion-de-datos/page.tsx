import PublicDoc from "@/components/PublicDoc";
import DeletionForm from "@/components/DeletionForm";

export const metadata = { title: "Eliminación de datos · Brasper" };

export default function EliminacionDeDatos() {
  return (
    <PublicDoc slug="eliminacion-de-datos" fallbackTitle="Eliminación de datos">
      <DeletionForm />
    </PublicDoc>
  );
}
