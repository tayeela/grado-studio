//! Поле, которого в файле может не быть, может быть `null` или значение — три разных случая. Обычный `Option`
//! склеил бы «нет поля» и `null`, и запись изменила бы файл. `Maybe` держит все три, поэтому файл после
//! чтения и записи совпадает с исходным по значению.

use serde::{Deserialize, Deserializer, Serialize, Serializer};

#[derive(Debug, Clone, PartialEq, Default)]
pub enum Maybe<T> {
    #[default]
    Absent,
    Null,
    Some(T),
}

impl<T> Maybe<T> {
    pub fn is_absent(&self) -> bool {
        matches!(self, Maybe::Absent)
    }
    pub fn get(&self) -> Option<&T> {
        match self {
            Maybe::Some(v) => Some(v),
            _ => None,
        }
    }
    pub fn get_mut(&mut self) -> Option<&mut T> {
        match self {
            Maybe::Some(v) => Some(v),
            _ => None,
        }
    }
}

impl<T: Serialize> Serialize for Maybe<T> {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        match self {
            Maybe::Some(v) => v.serialize(s),
            _ => s.serialize_none(),
        }
    }
}

impl<'de, T: Deserialize<'de>> Deserialize<'de> for Maybe<T> {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        Ok(match Option::<T>::deserialize(d)? {
            Some(v) => Maybe::Some(v),
            None => Maybe::Null,
        })
    }
}
