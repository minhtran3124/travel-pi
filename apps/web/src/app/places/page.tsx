"use client";

import { useState } from "react";

import { BrowseDrawer } from "@/components/places/BrowseDrawer";
import { SavedPlaceCard } from "@/components/places/SavedPlaceCard";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import {
  DuplicatePlaceError,
  useCreateSavedPlace,
  useDeleteSavedPlace,
  useSavedPlaces,
  useSetFavorite,
  useSetVisited,
  type Place,
  type SavedPlaceCreate,
  type SavedPlaceFilters,
} from "@/lib/query/places";

interface Notice {
  tone: "info" | "error";
  message: string;
}

function placeToCreate(place: Place): SavedPlaceCreate {
  return {
    name: place.name,
    city: place.city,
    country: place.country,
    category: place.category,
    address: place.address,
    latitude: place.latitude,
    longitude: place.longitude,
    price_level: place.price_level,
    favorite: false,
    visited: false,
  };
}

export default function PlacesPage() {
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [visitedOnly, setVisitedOnly] = useState(false);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);

  const filters: SavedPlaceFilters = {
    ...(favoriteOnly ? { favorite: true } : {}),
    ...(visitedOnly ? { visited: true } : {}),
  };
  const hasFilters = Object.keys(filters).length > 0;

  const { data, isLoading, isError } = useSavedPlaces(
    hasFilters ? filters : undefined,
  );
  const createPlace = useCreateSavedPlace();
  const deletePlace = useDeleteSavedPlace();
  const setFavorite = useSetFavorite();
  const setVisited = useSetVisited();

  const places = data?.results ?? [];

  function reportCreateError(err: unknown) {
    if (err instanceof DuplicatePlaceError) {
      setNotice({
        tone: "info",
        message: err.hint
          ? `Already in your saved places (${err.hint}).`
          : "This place is already in your saved places.",
      });
      return;
    }
    setNotice({ tone: "error", message: "Could not save the place. Try again." });
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setNotice(null);
    try {
      await createPlace.mutateAsync({
        name: name.trim(),
        city: city.trim() || undefined,
        favorite: false,
        visited: false,
      });
      setName("");
      setCity("");
      setNotice({ tone: "info", message: "Place saved." });
    } catch (err) {
      reportCreateError(err);
    }
  }

  async function handlePick(place: Place) {
    setNotice(null);
    try {
      await createPlace.mutateAsync(placeToCreate(place));
      setBrowseOpen(false);
      setNotice({ tone: "info", message: `Saved "${place.name}".` });
    } catch (err) {
      reportCreateError(err);
    }
  }

  const flagBusy = setFavorite.isPending || setVisited.isPending;

  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-lg px-xl py-lg">
      <header className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-2xl font-extrabold text-ink">Saved places</h1>
        <Button onClick={() => setBrowseOpen(true)}>Browse catalog</Button>
      </header>

      <form
        onSubmit={handleAdd}
        className="flex flex-wrap items-end gap-sm rounded-md border border-line bg-panel p-md"
      >
        <Field
          label="Name"
          placeholder="Secret rooftop bar"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoComplete="off"
          data-1p-ignore
          data-lpignore="true"
          wrapperClassName="min-w-[12rem] flex-[2]"
        />
        <Field
          label="City"
          placeholder="Hanoi"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          autoComplete="off"
          data-1p-ignore
          data-lpignore="true"
          wrapperClassName="min-w-[8rem] flex-1"
        />
        <Button
          type="submit"
          disabled={createPlace.isPending || !name.trim()}
          className="shrink-0"
        >
          {createPlace.isPending ? "Adding…" : "Add place"}
        </Button>
      </form>

      {notice ? (
        <p
          role={notice.tone === "error" ? "alert" : "status"}
          className={[
            "rounded-sm px-md py-sm text-sm font-semibold",
            notice.tone === "error"
              ? "bg-panel-raised text-muted"
              : "bg-panel-raised text-ink",
          ].join(" ")}
        >
          {notice.message}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-xs">
        <Button
          variant={favoriteOnly ? "primary" : "ghost"}
          aria-pressed={favoriteOnly}
          onClick={() => setFavoriteOnly((v) => !v)}
        >
          ★ Favorites
        </Button>
        <Button
          variant={visitedOnly ? "primary" : "ghost"}
          aria-pressed={visitedOnly}
          onClick={() => setVisitedOnly((v) => !v)}
        >
          ✓ Visited
        </Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-xl">
          <Spinner label="Loading saved places" />
        </div>
      ) : isError ? (
        <EmptyState
          icon="⚠️"
          title="Could not load saved places"
          hint="Something went wrong reaching the server."
        />
      ) : places.length === 0 ? (
        <EmptyState
          icon="📍"
          title="No saved places yet"
          hint={
            hasFilters
              ? "No places match these filters."
              : "Add one above or browse the catalog to get started."
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-3">
          {places.map((place) => (
            <SavedPlaceCard
              key={place.id}
              place={place}
              busy={flagBusy || deletePlace.isPending}
              onSetFavorite={(value) =>
                setFavorite.mutate({ id: place.id, value })
              }
              onSetVisited={(value) =>
                setVisited.mutate({ id: place.id, value })
              }
              onDelete={() => deletePlace.mutate(place.id)}
            />
          ))}
        </div>
      )}

      <BrowseDrawer
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        onPick={(place) => handlePick(place)}
      />
    </section>
  );
}
